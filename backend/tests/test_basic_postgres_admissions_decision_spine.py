"""Opt-in PostgreSQL 17 acceptance proof for the 0039 admissions spine.

The proof owns one fresh ``caresync`` database on an explicitly supplied
disposable loopback cluster.  It exercises migration and downgrade with a
NOBYPASSRLS migration owner, then drives the HTTP command surface through the
restricted runtime role.  Retained CareSync ports are rejected.

Run with, for example::

    BASIC_POSTGRES_ADMISSIONS_TEST_URL=\
postgresql+psycopg://postgres@127.0.0.1:56554/postgres \
      ./scripts/uv.sh run pytest -q \
      tests/test_basic_postgres_admissions_decision_spine.py
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
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
ADMIN_URL_TEXT = os.getenv("BASIC_POSTGRES_ADMISSIONS_TEST_URL")

DATABASE_NAME = "caresync"
PREVIOUS_REVISION = "0038_public_job_catalog_outbox"
CURRENT_REVISION = "0039_admissions_decision_spine"
MIGRATION_ROLE = "caresync_0039_migration_owner"
MIGRATION_PASSWORD = "disposable-0039-migration-only"
RUNTIME_ROLE = "caresync_basic_app"
RUNTIME_PASSWORD = "disposable-0039-runtime-only"
TRANSPORT_OWNER_ROLE = "caresync_transport_command_owner"
TRANSPORT_INGEST_ROLE = "caresync_transport_evidence_ingest"
HOSTILE_SCHEMA = MIGRATION_ROLE
DISPOSABLE_PORT = 56554
PROTECTED_PORTS = {5432, 5433, 5434, 56544, 56546, 56552, 56553}

ADMISSION_TABLES = (
    "admission_applications",
    "admission_application_preferences",
    "admission_waitlist_entries",
    "admission_offers",
    "admission_conversion_links",
    "admission_application_events",
)
IMMUTABLE_ADMISSION_TABLES = {
    "admission_conversion_links",
    "admission_application_events",
}
EXPECTED_UPDATE_COLUMNS = {
    "admission_applications": {
        "status",
        "version",
        "child_first_name",
        "child_last_name",
        "child_normalized_name",
        "child_date_of_birth",
        "contact_first_name",
        "contact_last_name",
        "contact_relationship",
        "contact_email",
        "contact_normalized_email",
        "contact_telephone",
        "contact_normalized_telephone",
        "internal_note",
        "updated_by_user_id",
        "last_operation_id",
        "submitted_at",
        "review_started_at",
        "terminal_at",
        "updated_at",
    },
    "admission_application_preferences": {
        "current_rank",
        "current_lane_key",
        "retired_by_user_id",
        "retired_operation_id",
        "retired_at",
    },
    "admission_waitlist_entries": {
        "current_application_id",
        "status",
        "version",
        "closure_reason",
        "updated_by_user_id",
        "last_operation_id",
        "closed_at",
        "updated_at",
    },
    "admission_offers": {
        "open_application_id",
        "status",
        "version",
        "updated_by_user_id",
        "last_operation_id",
        "withdrawn_at",
        "declined_at",
        "accepted_at",
        "updated_at",
    },
    "admission_conversion_links": set(),
    "admission_application_events": set(),
}


def _guard_admin_url(value: str) -> URL:
    url = make_url(value)
    if not url.drivername.startswith("postgresql"):
        raise RuntimeError("0039 acceptance requires PostgreSQL")
    if (url.host or "").strip().lower() not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError("0039 acceptance requires a loopback host")
    if (
        url.port is None
        or url.port in PROTECTED_PORTS
        or url.port != DISPOSABLE_PORT
        or not 1 <= url.port <= 65535
    ):
        raise RuntimeError("0039 acceptance refuses retained or invalid ports")
    if url.database != "postgres" or not url.username:
        raise RuntimeError(
            "0039 acceptance URL must target postgres as a cluster administrator"
        )
    return url


ADMIN_URL = _guard_admin_url(ADMIN_URL_TEXT) if ADMIN_URL_TEXT else None
pytestmark = pytest.mark.skipif(
    ADMIN_URL is None,
    reason=(
        "BASIC_POSTGRES_ADMISSIONS_TEST_URL must name a fresh disposable "
        "loopback PostgreSQL 17 cluster"
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


def _migration_environment(*, as_admin: bool = False) -> dict[str, str]:
    assert ADMIN_URL is not None
    environment = os.environ.copy()
    database_user = (
        str(ADMIN_URL.username) if as_admin else MIGRATION_ROLE
    )
    database_password = (
        str(ADMIN_URL.password or "") if as_admin else MIGRATION_PASSWORD
    )
    environment.update(
        {
            "ENVIRONMENT": "test",
            "DATABASE_TYPE": "postgres",
            "DATABASE_HOST": str(ADMIN_URL.host),
            "DATABASE_PORT": str(ADMIN_URL.port),
            "DATABASE_USER": database_user,
            "DATABASE_PASSWORD": database_password,
            "DATABASE_NAME": DATABASE_NAME,
            "DATABASE_SSL": "false",
            "DATABASE_READ_ONLY": "false",
            "PGCLIENTENCODING": "UTF8",
        }
    )
    return environment


def _alembic(
    action: str,
    revision: str,
    *,
    as_admin: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", action, revision],
        cwd=BACKEND_ROOT,
        env=_migration_environment(as_admin=as_admin),
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


def _settings() -> Settings:
    assert ADMIN_URL is not None
    return Settings(
        _env_file=None,
        environment="test",
        database_type="postgres",
        database_host=str(ADMIN_URL.host),
        database_port=int(ADMIN_URL.port or 0),
        database_user=RUNTIME_ROLE,
        database_password=RUNTIME_PASSWORD,
        database_name=DATABASE_NAME,
        database_ssl=False,
        database_read_only=False,
        enable_advanced_routes=False,
        jwt_secret="postgres-0039-admissions-test-secret-at-least-32-bytes",
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
) -> dict[str, dict]:
    auth = _post(
        client,
        "/api/v1/auth/register",
        {},
        {
            "email": f"admission-source-{marker}@example.test",
            "password": "secure-password-123",
            "first_name": "Source",
            "last_name": marker.title(),
            "organization_name": f"0039 Source {marker.title()}",
        },
    )
    headers = _headers(auth)
    facility = _post(
        client,
        "/api/v1/facilities",
        headers,
        {
            "name": f"{marker.title()} Centre",
            "licensed_capacity": 40,
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
            "capacity": 40,
            "minimum_age_months": 0,
            "maximum_age_months": 71,
        },
    )
    family = _post(
        client,
        "/api/v1/families",
        headers,
        {
            "client_operation_id": str(uuid4()),
            "name": f"{marker.title()} Existing Family",
        },
    )
    child = _post(
        client,
        "/api/v1/children",
        headers,
        {
            "client_operation_id": str(uuid4()),
            "family_id": family["id"],
            "first_name": f"Existing{marker.title()}",
            "last_name": "Child",
            "date_of_birth": "2023-02-01",
        },
    )
    enrollment = _post(
        client,
        f"/api/v1/children/{child['id']}/enrollments",
        headers,
        {
            "client_operation_id": str(uuid4()),
            "facility_id": facility["id"],
            "start_date": "2026-09-01",
        },
    )
    return {
        "auth": auth,
        "headers": headers,
        "facility": facility,
        "program": program,
        "family": family,
        "child": child,
        "enrollment": enrollment,
    }


def _intake(
    source: dict[str, dict],
    *,
    marker: str,
    operation_id=None,
) -> dict:
    return {
        "client_operation_id": str(operation_id or uuid4()),
        "child": {
            "first_name": f"Prospective{marker}",
            "last_name": "Admission",
            "date_of_birth": "2023-05-04",
        },
        "primary_contact": {
            "first_name": f"Contact{marker}",
            "last_name": "Admission",
            "relationship": "Parent",
            "email": f"admission-{marker.lower()}@example.test",
            "telephone": "780-555-0199",
        },
        "preferences": [
            {
                "rank": 1,
                "facility_id": source["facility"]["id"],
                "program_id": source["program"]["id"],
                "desired_start_date": "2026-09-01",
            }
        ],
        "internal_note": f"Private 0039 test note {marker}",
    }


def _version(version: int, **extra) -> dict:
    return {
        "client_operation_id": str(uuid4()),
        "expected_application_version": version,
        **extra,
    }


def _create_reviewed(
    client: TestClient,
    source: dict[str, dict],
    *,
    marker: str,
) -> dict:
    created = _post(
        client,
        "/api/v1/admissions/applications",
        source["headers"],
        _intake(source, marker=marker),
    )
    submitted = _post(
        client,
        f"/api/v1/admissions/applications/{created['id']}/submit",
        source["headers"],
        _version(created["version"]),
    )
    return _post(
        client,
        f"/api/v1/admissions/applications/{created['id']}/review/start",
        source["headers"],
        _version(submitted["version"]),
    )


def _issue_offer(
    client: TestClient,
    source: dict[str, dict],
    application: dict,
) -> dict:
    return _post(
        client,
        f"/api/v1/admissions/applications/{application['id']}/offers",
        source["headers"],
        _version(
            application["version"],
            facility_id=source["facility"]["id"],
            program_id=source["program"]["id"],
            proposed_start_date="2026-09-01",
            respond_by_date="2026-08-20",
        ),
    )


def _offered_matching_child(
    client: TestClient,
    source: dict[str, dict],
    child: dict,
    *,
    marker: str,
) -> dict:
    intake = _intake(source, marker=marker)
    intake["child"] = {
        "first_name": child["first_name"],
        "last_name": child["last_name"],
        "date_of_birth": child["date_of_birth"],
    }
    created = _post(
        client,
        "/api/v1/admissions/applications",
        source["headers"],
        intake,
    )
    submitted = _post(
        client,
        f"/api/v1/admissions/applications/{created['id']}/submit",
        source["headers"],
        _version(created["version"]),
    )
    reviewed = _post(
        client,
        f"/api/v1/admissions/applications/{created['id']}/review/start",
        source["headers"],
        _version(submitted["version"]),
    )
    return _issue_offer(client, source, reviewed)


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
            barrier.wait(timeout=15)
            response = client.post(path, headers=headers, json=payload)
            return response.status_code, response.json()

    with ThreadPoolExecutor(max_workers=len(payloads)) as executor:
        return list(executor.map(run, payloads))


def _parallel_requests(
    settings: Settings,
    requests: list[tuple[str, str, dict[str, str], dict]],
) -> list[tuple[int, dict]]:
    barrier = Barrier(len(requests))

    def run(
        request: tuple[str, str, dict[str, str], dict],
    ) -> tuple[int, dict]:
        method, path, headers, payload = request
        with TestClient(create_app(settings)) as client:
            barrier.wait(timeout=15)
            response = client.request(
                method,
                path,
                headers=headers,
                json=payload,
            )
            return response.status_code, response.json()

    with ThreadPoolExecutor(max_workers=len(requests)) as executor:
        return list(executor.map(run, requests))


def _set_context(
    connection,
    *,
    user_id: str,
    organization_id: str,
    operation_id: UUID | str | None = None,
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
                "'app.current_childcare_operation_id',:value,true)"
            ),
            {"value": str(operation_id)},
        )


def _table_counts(connection, tables: tuple[str, ...] | None = None) -> dict[str, int]:
    selected = tables or tuple(
        connection.execute(
            text(
                "SELECT tablename FROM pg_catalog.pg_tables "
                "WHERE schemaname='public' AND tablename<>'alembic_version' "
                "ORDER BY tablename"
            )
        ).scalars()
    )
    return {
        table_name: int(
            connection.scalar(
                text(f'SELECT count(*) FROM public."{table_name}"')
            )
            or 0
        )
        for table_name in selected
    }


def _canonical_digest(connection) -> str:
    payload: list[tuple[str, ...]] = []
    statements = {
        "families": (
            "SELECT id::text,organization_id::text,name,status,version::text "
            "FROM public.families ORDER BY organization_id,id"
        ),
        "children": (
            "SELECT id::text,organization_id::text,family_id::text,"
            "first_name,last_name,date_of_birth::text,is_active::text,version::text "
            "FROM public.children ORDER BY organization_id,id"
        ),
        "enrollments": (
            "SELECT id::text,organization_id::text,child_id::text,facility_id::text,"
            "coalesce(program_id::text,''),coalesce(room_id::text,''),"
            "start_date::text,status,version::text "
            "FROM public.enrollments ORDER BY organization_id,id"
        ),
    }
    for table_name, statement in statements.items():
        payload.extend(
            (table_name, *(str(value) for value in row))
            for row in connection.execute(text(statement))
        )
    return hashlib.sha256(
        json.dumps(payload, separators=(",", ":")).encode()
    ).hexdigest()


def _schema_fingerprint(connection) -> str:
    tables = list(ADMISSION_TABLES)
    parts: list[tuple] = []
    parts.extend(
        ("column", *row)
        for row in connection.execute(
            text(
                "SELECT table_name,column_name,data_type,is_nullable,"
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
        ("rls", *row)
        for row in connection.execute(
            text(
                "SELECT relname,relrowsecurity,relforcerowsecurity "
                "FROM pg_catalog.pg_class "
                "WHERE relname=ANY(CAST(:tables AS text[])) ORDER BY relname"
            ),
            {"tables": tables},
        )
    )
    return hashlib.sha256(
        json.dumps(parts, default=str, separators=(",", ":")).encode()
    ).hexdigest()


def _admission_counts(connection) -> dict[str, int]:
    return _table_counts(connection, ADMISSION_TABLES)


def _admission_security_snapshot(connection) -> list[tuple]:
    return list(
        connection.execute(
            text(
                "SELECT relation.relname,relation.relrowsecurity,"
                "relation.relforcerowsecurity,"
                "coalesce(string_agg(policy.policyname || ':' || policy.cmd || ':' || "
                "coalesce(policy.qual,'') || ':' || coalesce(policy.with_check,''),"
                "'|' ORDER BY policy.policyname),'') "
                "FROM pg_catalog.pg_class AS relation "
                "LEFT JOIN pg_catalog.pg_policies AS policy "
                "ON policy.schemaname='public' AND policy.tablename=relation.relname "
                "WHERE relation.relname=ANY(CAST(:tables AS text[])) "
                "GROUP BY relation.relname,relation.relrowsecurity,"
                "relation.relforcerowsecurity ORDER BY relation.relname"
            ),
            {"tables": list(ADMISSION_TABLES)},
        )
    )


def _assert_catalog_and_acl(connection) -> None:
    relation_security = {
        row.relname: (row.relrowsecurity, row.relforcerowsecurity)
        for row in connection.execute(
            text(
                "SELECT relname,relrowsecurity,relforcerowsecurity "
                "FROM pg_catalog.pg_class "
                "WHERE relname=ANY(CAST(:tables AS text[]))"
            ),
            {"tables": list(ADMISSION_TABLES)},
        )
    }
    assert relation_security == {
        table_name: (True, True) for table_name in ADMISSION_TABLES
    }

    policies = list(
        connection.execute(
            text(
                "SELECT tablename,policyname,cmd,qual,with_check "
                "FROM pg_catalog.pg_policies WHERE schemaname='public' "
                "AND tablename=ANY(CAST(:tables AS text[])) "
                "ORDER BY tablename,policyname"
            ),
            {"tables": list(ADMISSION_TABLES)},
        )
    )
    assert len(policies) == len(ADMISSION_TABLES)
    for policy in policies:
        assert policy.policyname == f"{policy.tablename}_tenant"
        assert policy.cmd == "ALL"
        assert "app.current_organization_id" in str(policy.qual)
        assert "app.current_organization_id" in str(policy.with_check)

    for table_name in ADMISSION_TABLES:
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
                text(
                    "SELECT has_table_privilege(:role,:table,:privilege)"
                ),
                {
                    "role": RUNTIME_ROLE,
                    "table": relation,
                    "privilege": forbidden,
                },
            )

    immutable_triggers = set(
        connection.execute(
            text(
                "SELECT relation.relname,trigger.tgname "
                "FROM pg_catalog.pg_trigger AS trigger "
                "JOIN pg_catalog.pg_class AS relation "
                "ON relation.oid=trigger.tgrelid "
                "WHERE relation.relname=ANY(CAST(:tables AS text[])) "
                "AND NOT trigger.tgisinternal"
            ),
            {"tables": list(IMMUTABLE_ADMISSION_TABLES)},
        )
    )
    assert immutable_triggers == {
        (
            "admission_application_events",
            "admission_application_events_command_bundle",
        ),
        (
            "admission_application_events",
            "admission_application_events_command_row",
        ),
        (
            "admission_application_events",
            "admission_application_events_immutable",
        ),
        (
            "admission_conversion_links",
            "admission_conversion_links_command_bundle",
        ),
        (
            "admission_conversion_links",
            "admission_conversion_links_command_row",
        ),
        ("admission_conversion_links", "admission_conversion_links_immutable"),
        (
            "admission_conversion_links",
            "admission_conversion_links_conversion_coherence",
        ),
    }

    coherence = {
        row.tgname: (row.tgdeferrable, row.tginitdeferred)
        for row in connection.execute(
            text(
                "SELECT trigger.tgname,trigger.tgdeferrable,trigger.tginitdeferred "
                "FROM pg_catalog.pg_trigger AS trigger "
                "WHERE trigger.tgname IN "
                "('admission_applications_conversion_coherence',"
                "'admission_offers_conversion_coherence',"
                "'admission_conversion_links_conversion_coherence')"
            )
        )
    }
    assert coherence == {
        "admission_applications_conversion_coherence": (True, True),
        "admission_offers_conversion_coherence": (True, True),
        "admission_conversion_links_conversion_coherence": (True, True),
    }

    command_guards = {
        (row.relname, row.tgname): (row.tgdeferrable, row.tginitdeferred)
        for row in connection.execute(
            text(
                "SELECT relation.relname,trigger.tgname,"
                "trigger.tgdeferrable,trigger.tginitdeferred "
                "FROM pg_catalog.pg_trigger AS trigger "
                "JOIN pg_catalog.pg_class AS relation "
                "ON relation.oid=trigger.tgrelid "
                "WHERE relation.relname=ANY(CAST(:tables AS text[])) "
                "AND (trigger.tgname LIKE '%_command_row' "
                "OR trigger.tgname LIKE '%_command_bundle') "
                "AND NOT trigger.tgisinternal"
            ),
            {"tables": list(ADMISSION_TABLES)},
        )
    }
    assert command_guards == {
        **{
            (table_name, f"{table_name}_command_row"): (False, False)
            for table_name in ADMISSION_TABLES
        },
        **{
            (table_name, f"{table_name}_command_bundle"): (True, True)
            for table_name in ADMISSION_TABLES
        },
    }

    for signature in (
        "caresync_0039_immutable_fact()",
        "caresync_0039_waitlist_priority_guard()",
        "caresync_0039_active_program_guard()",
        "caresync_0039_conversion_coherence_guard()",
        "caresync_0039_command_row_guard()",
        "caresync_0039_command_bundle_guard()",
    ):
        assert not connection.scalar(
            text(
                "SELECT has_function_privilege(:role,:function,'EXECUTE')"
            ),
            {"role": RUNTIME_ROLE, "function": f"public.{signature}"},
        )


def _mark_accepted(
    connection,
    *,
    application_id: str,
    offer_id: str,
    actor_user_id: str,
    operation_id: UUID,
) -> None:
    connection.execute(
        text(
            "UPDATE public.admission_offers SET status='accepted',"
            "open_application_id=NULL,accepted_at=now(),version=version+1,"
            "updated_by_user_id=:actor_user_id,"
            "last_operation_id=:operation_id,updated_at=now() "
            "WHERE id=:offer_id"
        ),
        {
            "actor_user_id": actor_user_id,
            "operation_id": operation_id,
            "offer_id": offer_id,
        },
    )
    connection.execute(
        text(
            "UPDATE public.admission_applications SET status='accepted',"
            "terminal_at=now(),version=version+1,"
            "updated_by_user_id=:actor_user_id,"
            "last_operation_id=:operation_id,updated_at=now() "
            "WHERE id=:application_id"
        ),
        {
            "actor_user_id": actor_user_id,
            "operation_id": operation_id,
            "application_id": application_id,
        },
    )


def _insert_conversion(
    connection,
    *,
    organization_id: str,
    application_id: str,
    offer_id: str,
    family_id: str,
    child_id: str,
    enrollment_id: str,
    actor_user_id: str,
    operation_id: UUID,
) -> None:
    connection.execute(
        text(
            "INSERT INTO public.admission_conversion_links "
            "(id,organization_id,application_id,offer_id,family_id,child_id,"
            "enrollment_id,resolution_mode,acceptance_operation_id,"
            "review_proof_digest,converted_by_user_id) VALUES "
            "(:id,:organization_id,:application_id,:offer_id,:family_id,:child_id,"
            ":enrollment_id,'reuse_child',:operation_id,:digest,:actor_user_id)"
        ),
        {
            "id": uuid4(),
            "organization_id": organization_id,
            "application_id": application_id,
            "offer_id": offer_id,
            "family_id": family_id,
            "child_id": child_id,
            "enrollment_id": enrollment_id,
            "operation_id": operation_id,
            "digest": "a" * 64,
            "actor_user_id": actor_user_id,
        },
    )


def test_postgres_0039_migration_rls_commands_guards_and_concurrency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert ADMIN_URL is not None
    # Some deliberately minimal scratch clusters use SQL_ASCII.  Pinning the
    # client to UTF-8 keeps psycopg/SQLAlchemy text decoding deterministic
    # without weakening the database target guard.
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
                    "SELECT 1 FROM pg_catalog.pg_database WHERE datname=:database"
                ),
                {"database": DATABASE_NAME},
            ) is None, "The 0039 acceptance gate requires a fresh cluster"
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
                "The 0039 acceptance gate requires unused CareSync role names: "
                f"{sorted(occupied)}"
            )
            connection.exec_driver_sql(
                f"CREATE ROLE {MIGRATION_ROLE} LOGIN PASSWORD "
                f"'{MIGRATION_PASSWORD}' NOSUPERUSER NOCREATEDB NOCREATEROLE "
                "NOREPLICATION NOINHERIT NOBYPASSRLS"
            )
            created_roles.add(MIGRATION_ROLE)
            connection.exec_driver_sql(
                f"ALTER ROLE {MIGRATION_ROLE} "
                "SET search_path TO public, pg_catalog"
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
                    f"CREATE SCHEMA {HOSTILE_SCHEMA} "
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

        # Build the entire retained lineage through 0038 as the deliberately
        # restricted migration owner.  The sole historical exception is the
        # already-certified 0033 immutable-source guard: production requires
        # that SECURITY DEFINER function to retain a privileged owner, exactly
        # as the dedicated 0038 PostgreSQL acceptance proof establishes.
        _require_success(_alembic("upgrade", PREVIOUS_REVISION))
        with database_admin.begin() as connection:
            connection.exec_driver_sql(
                "ALTER FUNCTION "
                "public.caresync_0033_attested_source_immutable() "
                f"OWNER TO {ADMIN_URL.username}"
            )
            immutable_source_owner = connection.execute(
                text(
                    "SELECT owner.rolname,owner.rolsuper,owner.rolbypassrls "
                    "FROM pg_catalog.pg_proc AS procedure "
                    "JOIN pg_catalog.pg_roles AS owner "
                    "ON owner.oid=procedure.proowner "
                    "WHERE procedure.oid=pg_catalog.to_regprocedure("
                    "'public.caresync_0033_attested_source_immutable()')"
                )
            ).one()
            assert immutable_source_owner[0] != MIGRATION_ROLE
            assert immutable_source_owner[1] or immutable_source_owner[2]
        first_bootstrap = _bootstrap()
        assert first_bootstrap.returncode == 0, (
            first_bootstrap.stdout + first_bootstrap.stderr
        )
        created_roles.update(
            {RUNTIME_ROLE, TRANSPORT_OWNER_ROLE, TRANSPORT_INGEST_ROLE}
        )
        with database_admin.begin() as connection:
            connection.exec_driver_sql(
                f"ALTER ROLE {RUNTIME_ROLE} PASSWORD '{RUNTIME_PASSWORD}'"
            )

        settings = _settings()
        # Source seeding deliberately bypasses the current-code lifespan: an
        # already valid 0038 database predates the 0039 runtime capability.
        # The full restricted startup gate is exercised after the second
        # 0039 upgrade and bootstrap below.
        source_client = TestClient(create_app(settings))
        try:
            source_a = _seed_source_tenant(source_client, marker="alpha")
            source_b = _seed_source_tenant(source_client, marker="beta")
        finally:
            source_client.close()

        with database_admin.begin() as connection:
            source_tables = tuple(
                connection.execute(
                    text(
                        "SELECT tablename FROM pg_catalog.pg_tables "
                        "WHERE schemaname='public' "
                        "AND tablename<>'alembic_version' ORDER BY tablename"
                    )
                ).scalars()
            )
            source_counts = _table_counts(connection, source_tables)
            source_digest = _canonical_digest(connection)
            owner_permissions = connection.scalar(
                text(
                    "SELECT permissions FROM public.roles "
                    "WHERE organization_id=:organization_id AND key='owner'"
                ),
                {
                    "organization_id": source_a["auth"]["user"][
                        "organization_id"
                    ]
                },
            )
            permissions = [
                str(value)
                for value in (owner_permissions or [])
                if not str(value).startswith("admissions:")
            ]
            permissions.append("custom:preserved")
            connection.execute(
                text(
                    "UPDATE public.roles SET permissions=CAST(:permissions AS jsonb) "
                    "WHERE organization_id=:organization_id AND key='owner'"
                ),
                {
                    "permissions": json.dumps(permissions),
                    "organization_id": source_a["auth"]["user"][
                        "organization_id"
                    ],
                },
            )
            assert connection.scalar(
                text(
                    "SELECT pg_catalog.pg_get_userbyid(relowner) "
                    "FROM pg_catalog.pg_class "
                    "WHERE oid='public.childcare_command_receipts'::regclass"
                )
            ) == MIGRATION_ROLE
            immutable_source_owner = connection.execute(
                text(
                    "SELECT owner.rolname,owner.rolsuper,owner.rolbypassrls "
                    "FROM pg_catalog.pg_proc AS procedure "
                    "JOIN pg_catalog.pg_roles AS owner "
                    "ON owner.oid=procedure.proowner "
                    "WHERE procedure.oid=pg_catalog.to_regprocedure("
                    "'public.caresync_0033_attested_source_immutable()')"
                )
            ).one()
            assert immutable_source_owner[0] != MIGRATION_ROLE
            assert immutable_source_owner[1] or immutable_source_owner[2]

        # M01/M02/M03: populated 0038 migration, empty round-trip, then
        # identical second upgrade under the hostile NOBYPASSRLS owner.
        with database_admin.begin() as connection:
            connection.exec_driver_sql(
                f'ALTER ROLE {MIGRATION_ROLE} SET search_path TO "$user", public'
            )
        hostile_owner = create_engine(_url(user=MIGRATION_ROLE))
        try:
            with hostile_owner.connect() as connection:
                assert connection.scalar(text("SHOW search_path")) == (
                    '"$user", public'
                )
                assert connection.scalar(text("SELECT current_schema()")) == (
                    HOSTILE_SCHEMA
                )
        finally:
            hostile_owner.dispose()
        _require_success(_alembic("upgrade", CURRENT_REVISION))
        with database_admin.connect() as connection:
            assert connection.scalar(
                text("SELECT version_num FROM public.alembic_version")
            ) == CURRENT_REVISION
            assert _table_counts(connection, source_tables) == source_counts
            assert _canonical_digest(connection) == source_digest
            assert _admission_counts(connection) == {
                table_name: 0 for table_name in ADMISSION_TABLES
            }
            permissions_after = set(
                connection.scalar(
                    text(
                        "SELECT permissions FROM public.roles "
                        "WHERE organization_id=:organization_id AND key='owner'"
                    ),
                    {
                        "organization_id": source_a["auth"]["user"][
                            "organization_id"
                        ]
                    },
                )
            )
            assert {
                "custom:preserved",
                "admissions:read",
                "admissions:manage",
                "admissions:decide",
            } <= permissions_after
            leaked_relations = connection.scalar(
                text(
                    "SELECT count(*) FROM pg_catalog.pg_class AS relation "
                    "JOIN pg_catalog.pg_namespace AS namespace "
                    "ON namespace.oid=relation.relnamespace "
                    "WHERE namespace.nspname=:schema"
                ),
                {"schema": HOSTILE_SCHEMA},
            )
            assert leaked_relations == 0
            first_fingerprint = _schema_fingerprint(connection)

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
                for table_name in ADMISSION_TABLES
            )
            downgraded_permissions = set(
                connection.scalar(
                    text(
                        "SELECT permissions FROM public.roles "
                        "WHERE organization_id=:organization_id AND key='owner'"
                    ),
                    {
                        "organization_id": source_a["auth"]["user"][
                            "organization_id"
                        ]
                    },
                )
            )
            assert "custom:preserved" in downgraded_permissions
            assert not any(
                value.startswith("admissions:")
                for value in downgraded_permissions
            )

        _require_success(_alembic("upgrade", CURRENT_REVISION))
        with database_admin.connect() as connection:
            assert _schema_fingerprint(connection) == first_fingerprint
            assert _table_counts(connection, source_tables) == source_counts
            assert _canonical_digest(connection) == source_digest

        second_bootstrap = _bootstrap()
        assert second_bootstrap.returncode == 0, (
            second_bootstrap.stdout + second_bootstrap.stderr
        )
        with database_admin.begin() as connection:
            connection.exec_driver_sql(
                f"ALTER ROLE {RUNTIME_ROLE} PASSWORD '{RUNTIME_PASSWORD}'"
            )
            _assert_catalog_and_acl(connection)
            receipt_constraint = " ".join(
                connection.execute(
                    text(
                        "SELECT pg_catalog.pg_get_constraintdef(oid) "
                        "FROM pg_catalog.pg_constraint "
                        "WHERE conrelid='public.childcare_command_receipts'::regclass "
                        "AND conname='ck_childcare_command_receipts_target'"
                    )
                ).scalars()
            )
            assert all(
                target in receipt_constraint
                for target in (
                    "admission_application",
                    "admission_waitlist",
                    "admission_offer",
                )
            )

        database = Database(settings)
        try:
            database.assert_basic_runtime_identity()
            assert database.has_admissions_decision_spine() is True
        finally:
            database.dispose()

        runtime = create_engine(_url(user=RUNTIME_ROLE))
        with TestClient(create_app(settings)) as client:
            second_facility = _post(
                client,
                "/api/v1/facilities",
                source_a["headers"],
                {
                    "name": "Alpha Second Centre",
                    "licensed_capacity": 30,
                    "status": "active",
                },
            )
            second_program = _post(
                client,
                "/api/v1/programs",
                source_a["headers"],
                {
                    "facility_id": second_facility["id"],
                    "name": "Alpha Second Daycare",
                    "program_type": "daycare",
                    "capacity": 30,
                    "minimum_age_months": 0,
                    "maximum_age_months": 71,
                },
            )
            first_lane = {
                "rank": 1,
                "facility_id": source_a["facility"]["id"],
                "program_id": source_a["program"]["id"],
                "desired_start_date": "2026-09-01",
            }
            second_lane = {
                "rank": 2,
                "facility_id": second_facility["id"],
                "program_id": second_program["id"],
                "desired_start_date": "2026-09-01",
            }
            forward_preferences = _intake(
                source_a,
                marker="ForwardPreferences",
            )
            forward_preferences["preferences"] = [first_lane, second_lane]
            reverse_preferences = _intake(
                source_a,
                marker="ReversePreferences",
            )
            reverse_preferences["preferences"] = [second_lane, first_lane]
            reversed_results = _parallel_post(
                settings,
                path="/api/v1/admissions/applications",
                headers=source_a["headers"],
                payloads=[forward_preferences, reverse_preferences],
            )
            assert [status for status, _body in reversed_results] == [201, 201]
            assert all(
                {
                    (
                        preference["rank"],
                        preference["facility_id"],
                        preference["program_id"],
                    )
                    for preference in body["preferences"]
                }
                == {
                    (
                        first_lane["rank"],
                        first_lane["facility_id"],
                        first_lane["program_id"],
                    ),
                    (
                        second_lane["rank"],
                        second_lane["facility_id"],
                        second_lane["program_id"],
                    ),
                }
                for _status, body in reversed_results
            )

            application_a = _post(
                client,
                "/api/v1/admissions/applications",
                source_a["headers"],
                _intake(source_a, marker="TenantAlpha"),
            )
            application_b = _post(
                client,
                "/api/v1/admissions/applications",
                source_b["headers"],
                _intake(source_b, marker="TenantBeta"),
            )

            # Forced RLS hides all rows without context and every other tenant
            # with an explicit context.  A same-tenant row carrying another
            # tenant's application identifier also fails its composite FK.
            with runtime.begin() as connection:
                assert connection.scalar(
                    text("SELECT count(*) FROM public.admission_applications")
                ) == 0
            with runtime.begin() as connection:
                _set_context(
                    connection,
                    user_id=source_a["auth"]["user"]["id"],
                    organization_id=source_a["auth"]["user"]["organization_id"],
                )
                visible_ids = list(
                    connection.execute(
                        text(
                            "SELECT id::text FROM public.admission_applications "
                            "ORDER BY id"
                        )
                    ).scalars()
                )
                assert set(visible_ids) == {
                    application_a["id"],
                    *(body["id"] for _status, body in reversed_results),
                }
            cross_tenant_operation_id = uuid4()
            with pytest.raises(DBAPIError), runtime.begin() as connection:
                _set_context(
                    connection,
                    user_id=source_a["auth"]["user"]["id"],
                    organization_id=source_a["auth"]["user"]["organization_id"],
                    operation_id=cross_tenant_operation_id,
                )
                connection.execute(
                    text(
                        "INSERT INTO public.admission_application_preferences "
                        "(id,organization_id,application_id,rank,current_rank,"
                        "current_lane_key,facility_id,program_id,"
                        "requested_start_date,application_version,"
                        "created_by_user_id,created_operation_id) VALUES "
                        "(:id,:organization_id,:application_id,2,2,:lane,"
                        ":facility_id,:program_id,DATE '2026-10-01',1,"
                        ":actor_user_id,:operation_id)"
                    ),
                    {
                        "id": uuid4(),
                        "organization_id": source_a["auth"]["user"][
                            "organization_id"
                        ],
                        "application_id": application_b["id"],
                        "lane": (
                            f"{source_a['facility']['id']}:"
                            f"{source_a['program']['id']}"
                        ),
                        "facility_id": source_a["facility"]["id"],
                        "program_id": source_a["program"]["id"],
                        "actor_user_id": source_a["auth"]["user"]["id"],
                        "operation_id": cross_tenant_operation_id,
                    },
                )

            cross_tenant = client.get(
                f"/api/v1/admissions/applications/{application_a['id']}",
                headers=source_b["headers"],
            )
            assert cross_tenant.status_code == 404

            with pytest.raises(DBAPIError), runtime.begin() as connection:
                _set_context(
                    connection,
                    user_id=source_a["auth"]["user"]["id"],
                    organization_id=source_a["auth"]["user"]["organization_id"],
                )
                connection.execute(
                    text(
                        "DELETE FROM public.admission_applications "
                        "WHERE id=:application_id"
                    ),
                    {"application_id": application_a["id"]},
                )

            # Column ACLs alone cannot forge a lifecycle transition.  This
            # direct runtime UPDATE satisfies the row-level provenance shape,
            # but commit is rejected because it lacks the single-operation
            # receipt/event/audit/realtime command bundle.
            forged_operation_id = uuid4()
            with pytest.raises(
                DBAPIError,
                match="admission command bundle is incomplete",
            ), runtime.begin() as connection:
                _set_context(
                    connection,
                    user_id=source_a["auth"]["user"]["id"],
                    organization_id=source_a["auth"]["user"]["organization_id"],
                    operation_id=forged_operation_id,
                )
                connection.execute(
                    text(
                        "UPDATE public.admission_applications "
                        "SET status='submitted',submitted_at=now(),"
                        "updated_by_user_id=:actor_user_id,"
                        "last_operation_id=:operation_id,version=version+1,"
                        "updated_at=now() WHERE id=:application_id"
                    ),
                    {
                        "actor_user_id": source_a["auth"]["user"]["id"],
                        "operation_id": forged_operation_id,
                        "application_id": application_a["id"],
                    },
                )
            canonical_after_forgery = client.get(
                f"/api/v1/admissions/applications/{application_a['id']}",
                headers=source_a["headers"],
            )
            assert canonical_after_forgery.status_code == 200
            assert canonical_after_forgery.json()["status"] == "draft"
            assert canonical_after_forgery.json()["version"] == 1

            # A disabled lane remains referentially valid but the dedicated
            # active-lane trigger rejects admission writes through runtime.
            with database_admin.begin() as connection:
                connection.execute(
                    text(
                        "UPDATE public.facility_programs SET is_active=false "
                        "WHERE id=:program_id"
                    ),
                    {"program_id": source_a["program"]["id"]},
                )
            try:
                with pytest.raises(
                    DBAPIError,
                    match="admission lane must use an active program",
                ), runtime.begin() as connection:
                    inactive_lane_operation_id = uuid4()
                    _set_context(
                        connection,
                        user_id=source_a["auth"]["user"]["id"],
                        organization_id=source_a["auth"]["user"][
                            "organization_id"
                        ],
                        operation_id=inactive_lane_operation_id,
                    )
                    connection.execute(
                        text(
                            "INSERT INTO "
                            "public.admission_application_preferences "
                            "(id,organization_id,application_id,rank,current_rank,"
                            "current_lane_key,facility_id,program_id,"
                            "requested_start_date,application_version,"
                            "created_by_user_id,created_operation_id) VALUES "
                            "(:id,:organization_id,:application_id,2,2,"
                            ":lane_key,:facility_id,:program_id,"
                            "DATE '2026-10-01',1,:actor_user_id,:operation_id)"
                        ),
                        {
                            "id": uuid4(),
                            "organization_id": source_a["auth"]["user"][
                                "organization_id"
                            ],
                            "application_id": application_a["id"],
                            "lane_key": f"inactive-probe:{uuid4()}",
                            "facility_id": source_a["facility"]["id"],
                            "program_id": source_a["program"]["id"],
                            "actor_user_id": source_a["auth"]["user"]["id"],
                            "operation_id": inactive_lane_operation_id,
                        },
                    )
            finally:
                with database_admin.begin() as connection:
                    connection.execute(
                        text(
                            "UPDATE public.facility_programs SET is_active=true "
                            "WHERE id=:program_id"
                        ),
                        {"program_id": source_a["program"]["id"]},
                    )

            # Optimistic lifecycle concurrency: both requests are valid when
            # sent, but the application row lock and version make one win.
            lifecycle = _post(
                client,
                "/api/v1/admissions/applications",
                source_a["headers"],
                _intake(source_a, marker="ConcurrentLifecycle"),
            )
            lifecycle_results = _parallel_post(
                settings,
                path=(
                    f"/api/v1/admissions/applications/{lifecycle['id']}/submit"
                ),
                headers=source_a["headers"],
                payloads=[
                    _version(lifecycle["version"]),
                    _version(lifecycle["version"]),
                ],
            )
            assert sorted(status for status, _body in lifecycle_results) == [
                200,
                409,
            ]
            assert {
                body["detail"]["code"]
                for status, body in lifecycle_results
                if status == 409
            } <= {
                "admission_version_conflict",
                "admission_transition_invalid",
            }

            # Two simultaneous waitlist commands create exactly one current
            # entry and one additional application establishes deterministic
            # lane position ordering.
            waitlist_candidate = _create_reviewed(
                client,
                source_a,
                marker="ConcurrentWaitlist",
            )
            waitlist_path = (
                f"/api/v1/admissions/applications/{waitlist_candidate['id']}"
                "/waitlist"
            )
            waitlist_payload = {
                "facility_id": source_a["facility"]["id"],
                "program_id": source_a["program"]["id"],
                "desired_start_date": "2026-09-01",
            }
            waitlist_results = _parallel_post(
                settings,
                path=waitlist_path,
                headers=source_a["headers"],
                payloads=[
                    _version(waitlist_candidate["version"], **waitlist_payload),
                    _version(waitlist_candidate["version"], **waitlist_payload),
                ],
            )
            assert sorted(status for status, _body in waitlist_results) == [
                200,
                409,
            ]
            current_waitlisted = client.get(
                (
                    "/api/v1/admissions/applications/"
                    f"{waitlist_candidate['id']}"
                ),
                headers=source_a["headers"],
            ).json()
            assert current_waitlisted["waitlist"]["status"] == "active"

            later_waitlist = _create_reviewed(
                client,
                source_a,
                marker="LaterWaitlist",
            )
            later_waitlist = _post(
                client,
                (
                    f"/api/v1/admissions/applications/{later_waitlist['id']}"
                    "/waitlist"
                ),
                source_a["headers"],
                _version(later_waitlist["version"], **waitlist_payload),
            )
            waitlist_directory = client.get(
                "/api/v1/admissions/waitlist",
                headers=source_a["headers"],
            )
            assert waitlist_directory.status_code == 200
            ordered = [
                item
                for item in waitlist_directory.json()["items"]
                if item["application_id"]
                in {current_waitlisted["id"], later_waitlist["id"]}
            ]
            assert [item["position"] for item in ordered] == [1, 2]

            # Open-offer concurrency is protected independently from the
            # optimistic application version.
            offer_candidate = _create_reviewed(
                client,
                source_a,
                marker="ConcurrentOffer",
            )
            offer_path = (
                f"/api/v1/admissions/applications/{offer_candidate['id']}"
                "/offers"
            )
            offer_payload = {
                "facility_id": source_a["facility"]["id"],
                "program_id": source_a["program"]["id"],
                "proposed_start_date": "2026-09-01",
                "respond_by_date": "2026-08-20",
            }
            offer_results = _parallel_post(
                settings,
                path=offer_path,
                headers=source_a["headers"],
                payloads=[
                    _version(offer_candidate["version"], **offer_payload),
                    _version(offer_candidate["version"], **offer_payload),
                ],
            )
            assert sorted(status for status, _body in offer_results) == [
                200,
                409,
            ]
            canonical_offer = client.get(
                (
                    "/api/v1/admissions/applications/"
                    f"{offer_candidate['id']}"
                ),
                headers=source_a["headers"],
            ).json()
            assert canonical_offer["offer"]["status"] == "open"

            # Acceptance and the canonical Enrollment creator share
            # Family -> Child -> Facility ordering.  One command wins and the
            # other observes the single open-enrollment invariant; neither may
            # surface a deadlock/500.
            enrollment_race_family = _post(
                client,
                "/api/v1/families",
                source_a["headers"],
                {
                    "client_operation_id": str(uuid4()),
                    "name": "Enrollment Race Family",
                },
            )
            enrollment_race_child = _post(
                client,
                "/api/v1/children",
                source_a["headers"],
                {
                    "client_operation_id": str(uuid4()),
                    "family_id": enrollment_race_family["id"],
                    "first_name": "EnrollmentRace",
                    "last_name": "Admission",
                    "date_of_birth": "2023-05-04",
                },
            )
            enrollment_race_offer = _offered_matching_child(
                client,
                source_a,
                enrollment_race_child,
                marker="EnrollmentRace",
            )
            enrollment_race_review_response = client.get(
                (
                    "/api/v1/admissions/applications/"
                    f"{enrollment_race_offer['id']}/conversion-candidates"
                ),
                headers=source_a["headers"],
            )
            assert enrollment_race_review_response.status_code == 200
            enrollment_race_review = enrollment_race_review_response.json()
            assert [
                candidate["id"]
                for candidate in enrollment_race_review["children"]
            ] == [enrollment_race_child["id"]]
            enrollment_race_results = _parallel_requests(
                settings,
                [
                    (
                        "POST",
                        (
                            "/api/v1/admissions/applications/"
                            f"{enrollment_race_offer['id']}/offers/"
                            f"{enrollment_race_offer['offer']['id']}"
                            "/accept-and-convert"
                        ),
                        source_a["headers"],
                        {
                            "client_operation_id": str(uuid4()),
                            "expected_application_version": (
                                enrollment_race_offer["version"]
                            ),
                            "expected_offer_version": (
                                enrollment_race_offer["offer"]["version"]
                            ),
                            "review_token": enrollment_race_review[
                                "review_token"
                            ],
                            "resolution_mode": "reuse_child",
                            "family_id": enrollment_race_family["id"],
                            "expected_family_version": (
                                enrollment_race_family["version"]
                            ),
                            "child_id": enrollment_race_child["id"],
                            "expected_child_version": (
                                enrollment_race_child["version"]
                            ),
                        },
                    ),
                    (
                        "POST",
                        (
                            f"/api/v1/children/{enrollment_race_child['id']}"
                            "/enrollments"
                        ),
                        source_a["headers"],
                        {
                            "client_operation_id": str(uuid4()),
                            "facility_id": source_a["facility"]["id"],
                            "start_date": "2026-09-01",
                        },
                    ),
                ],
            )
            assert sum(
                status_code < 300
                for status_code, _body in enrollment_race_results
            ) == 1
            assert sorted(
                status_code >= 500
                for status_code, _body in enrollment_race_results
            ) == [False, False]
            with database_admin.connect() as connection:
                assert connection.scalar(
                    text(
                        "SELECT count(*) FROM public.enrollments "
                        "WHERE organization_id=:organization_id "
                        "AND child_id=:child_id "
                        "AND status IN ('pending','active','paused')"
                    ),
                    {
                        "organization_id": source_a["auth"]["user"][
                            "organization_id"
                        ],
                        "child_id": enrollment_race_child["id"],
                    },
                ) == 1

            # A reparenting Child mutation locks both Families then the Child.
            # Acceptance must use the same class order, yielding one coherent
            # winner instead of Child->Family deadlock inversion.
            mutation_race_family = _post(
                client,
                "/api/v1/families",
                source_a["headers"],
                {
                    "client_operation_id": str(uuid4()),
                    "name": "Mutation Race Family",
                },
            )
            mutation_target_family = _post(
                client,
                "/api/v1/families",
                source_a["headers"],
                {
                    "client_operation_id": str(uuid4()),
                    "name": "Mutation Race Target Family",
                },
            )
            mutation_race_child = _post(
                client,
                "/api/v1/children",
                source_a["headers"],
                {
                    "client_operation_id": str(uuid4()),
                    "family_id": mutation_race_family["id"],
                    "first_name": "MutationRace",
                    "last_name": "Admission",
                    "date_of_birth": "2023-05-04",
                },
            )
            mutation_race_offer = _offered_matching_child(
                client,
                source_a,
                mutation_race_child,
                marker="MutationRace",
            )
            mutation_race_review_response = client.get(
                (
                    "/api/v1/admissions/applications/"
                    f"{mutation_race_offer['id']}/conversion-candidates"
                ),
                headers=source_a["headers"],
            )
            assert mutation_race_review_response.status_code == 200
            mutation_race_review = mutation_race_review_response.json()
            assert [
                candidate["id"]
                for candidate in mutation_race_review["children"]
            ] == [mutation_race_child["id"]]
            mutation_race_results = _parallel_requests(
                settings,
                [
                    (
                        "POST",
                        (
                            "/api/v1/admissions/applications/"
                            f"{mutation_race_offer['id']}/offers/"
                            f"{mutation_race_offer['offer']['id']}"
                            "/accept-and-convert"
                        ),
                        source_a["headers"],
                        {
                            "client_operation_id": str(uuid4()),
                            "expected_application_version": (
                                mutation_race_offer["version"]
                            ),
                            "expected_offer_version": (
                                mutation_race_offer["offer"]["version"]
                            ),
                            "review_token": mutation_race_review[
                                "review_token"
                            ],
                            "resolution_mode": "reuse_child",
                            "family_id": mutation_race_family["id"],
                            "expected_family_version": (
                                mutation_race_family["version"]
                            ),
                            "child_id": mutation_race_child["id"],
                            "expected_child_version": (
                                mutation_race_child["version"]
                            ),
                        },
                    ),
                    (
                        "PATCH",
                        f"/api/v1/children/{mutation_race_child['id']}",
                        source_a["headers"],
                        {
                            "client_operation_id": str(uuid4()),
                            "expected_version": mutation_race_child["version"],
                            "family_id": mutation_target_family["id"],
                        },
                    ),
                ],
            )
            assert sum(
                status_code < 300
                for status_code, _body in mutation_race_results
            ) == 1
            assert all(
                status_code < 500
                for status_code, _body in mutation_race_results
            )

            # Concurrent acceptance proves one atomic Family/Child/pending
            # unassigned Enrollment conversion and one canonical loser.
            conversion_candidate = _create_reviewed(
                client,
                source_a,
                marker=f"ConcurrentConversion{uuid4().hex[:8]}",
            )
            conversion_candidate = _issue_offer(
                client,
                source_a,
                conversion_candidate,
            )
            review_response = client.get(
                (
                    "/api/v1/admissions/applications/"
                    f"{conversion_candidate['id']}/conversion-candidates"
                ),
                headers=source_a["headers"],
            )
            assert review_response.status_code == 200, review_response.text
            review = review_response.json()
            assert review["families"] == []
            assert review["children"] == []
            with database_admin.connect() as connection:
                canonical_before_conversion = {
                    table_name: connection.scalar(
                        text(
                            f"SELECT count(*) FROM public.{table_name} "
                            "WHERE organization_id=:organization_id"
                        ),
                        {
                            "organization_id": source_a["auth"]["user"][
                                "organization_id"
                            ]
                        },
                    )
                    for table_name in ("families", "children", "enrollments")
                }
            acceptance_path = (
                f"/api/v1/admissions/applications/{conversion_candidate['id']}"
                f"/offers/{conversion_candidate['offer']['id']}"
                "/accept-and-convert"
            )
            acceptance_base = {
                "expected_application_version": conversion_candidate["version"],
                "expected_offer_version": conversion_candidate["offer"][
                    "version"
                ],
                "review_token": review["review_token"],
                "resolution_mode": "create_family_and_child",
            }
            acceptance_results = _parallel_post(
                settings,
                path=acceptance_path,
                headers=source_a["headers"],
                payloads=[
                    {
                        **acceptance_base,
                        "client_operation_id": str(uuid4()),
                    },
                    {
                        **acceptance_base,
                        "client_operation_id": str(uuid4()),
                    },
                ],
            )
            assert sorted(status for status, _body in acceptance_results) == [
                200,
                409,
            ]
            loser = next(
                body
                for status, body in acceptance_results
                if status == 409
            )
            assert loser["detail"]["code"] == "admission_already_converted"
            accepted = next(
                body
                for status, body in acceptance_results
                if status == 200
            )
            assert accepted["status"] == "accepted"
            assert accepted["offer"]["status"] == "accepted"
            assert accepted["conversion"] is not None

            with database_admin.connect() as connection:
                conversion_row = connection.execute(
                    text(
                        "SELECT id::text,acceptance_operation_id::text,"
                        "family_id::text,child_id::text,enrollment_id::text "
                        "FROM public.admission_conversion_links "
                        "WHERE application_id=:application_id"
                    ),
                    {"application_id": conversion_candidate["id"]},
                ).one()
                assert {
                    "family_id": conversion_row.family_id,
                    "child_id": conversion_row.child_id,
                    "enrollment_id": conversion_row.enrollment_id,
                } == {
                    "family_id": accepted["conversion"]["family_id"],
                    "child_id": accepted["conversion"]["child_id"],
                    "enrollment_id": accepted["conversion"]["enrollment_id"],
                }
                for table_name in ("families", "children", "enrollments"):
                    count_after = connection.scalar(
                        text(
                            f"SELECT count(*) FROM public.{table_name} "
                            "WHERE organization_id=:organization_id"
                        ),
                        {
                            "organization_id": source_a["auth"]["user"][
                                "organization_id"
                            ]
                        },
                    )
                    assert count_after == canonical_before_conversion[
                        table_name
                    ] + 1
                enrollment_shape = connection.execute(
                    text(
                        "SELECT status,program_id,room_id,"
                        "placement_effective_date FROM public.enrollments "
                        "WHERE id=:enrollment_id"
                    ),
                    {"enrollment_id": conversion_row.enrollment_id},
                ).one()
                assert enrollment_shape == ("pending", None, None, None)
                assert connection.scalar(
                    text(
                        "SELECT count(*) FROM public.childcare_command_receipts "
                        "WHERE organization_id=:organization_id "
                        "AND command_type IN "
                        "('admission.offer.accept_and_convert','family.create',"
                        "'child.create','enrollment.create') "
                        "AND target_id IN "
                        "(:offer_id,:family_id,:child_id,:enrollment_id)"
                    ),
                    {
                        "organization_id": source_a["auth"]["user"][
                            "organization_id"
                        ],
                        "offer_id": conversion_candidate["offer"]["id"],
                        "family_id": conversion_row.family_id,
                        "child_id": conversion_row.child_id,
                        "enrollment_id": conversion_row.enrollment_id,
                    },
                ) == 4

            # Database-level immutability remains effective even for the
            # migration owner/superuser, independent of runtime ACL denial.
            with (
                pytest.raises(DBAPIError, match="admission fact is immutable"),
                database_admin.begin() as connection,
            ):
                connection.execute(
                    text(
                        "UPDATE public.admission_conversion_links "
                        "SET acceptance_operation_id=:operation_id "
                        "WHERE id=:conversion_id"
                    ),
                    {
                        "operation_id": uuid4(),
                        "conversion_id": conversion_row.id,
                    },
                )
            with (
                pytest.raises(DBAPIError, match="admission fact is immutable"),
                database_admin.begin() as connection,
            ):
                connection.execute(
                    text(
                        "UPDATE public.admission_application_events "
                        "SET reason_code='tampered' "
                        "WHERE application_id=:application_id"
                    ),
                    {"application_id": conversion_candidate["id"]},
                )
            with pytest.raises(
                DBAPIError,
                match="waitlist priority is immutable",
            ), database_admin.begin() as connection:
                priority_operation_id = uuid4()
                _set_context(
                    connection,
                    user_id=source_a["auth"]["user"]["id"],
                    organization_id=source_a["auth"]["user"][
                        "organization_id"
                    ],
                    operation_id=priority_operation_id,
                )
                connection.execute(
                    text(
                        "UPDATE public.admission_waitlist_entries "
                        "SET priority_at=priority_at + interval '1 second',"
                        "version=version+1,"
                        "updated_by_user_id=:actor_user_id,"
                        "last_operation_id=:operation_id,updated_at=now() "
                        "WHERE application_id=:application_id"
                    ),
                    {
                        "actor_user_id": source_a["auth"]["user"]["id"],
                        "operation_id": priority_operation_id,
                        "application_id": current_waitlisted["id"],
                    },
                )
            with (
                pytest.raises(DBAPIError),
                database_admin.begin() as connection,
            ):
                duplicate_operation_id = uuid4()
                _set_context(
                    connection,
                    user_id=source_a["auth"]["user"]["id"],
                    organization_id=source_a["auth"]["user"][
                        "organization_id"
                    ],
                    operation_id=duplicate_operation_id,
                )
                connection.execute(
                    text(
                        "INSERT INTO public.admission_conversion_links "
                        "(id,organization_id,application_id,offer_id,"
                        "family_id,child_id,enrollment_id,resolution_mode,"
                        "acceptance_operation_id,review_proof_digest,"
                        "converted_by_user_id) "
                        "SELECT :id,organization_id,application_id,offer_id,"
                        "family_id,child_id,enrollment_id,resolution_mode,"
                        ":operation_id,review_proof_digest,"
                        "converted_by_user_id "
                        "FROM public.admission_conversion_links "
                        "WHERE id=:conversion_id"
                    ),
                    {
                        "id": uuid4(),
                        "operation_id": duplicate_operation_id,
                        "conversion_id": conversion_row.id,
                    },
                )

            # Deferred coherence rejects accepted heads without a conversion,
            # a conversion whose Enrollment belongs to another Child, and a
            # conversion whose Enrollment is no longer pending/unassigned.
            guard_candidate = _issue_offer(
                client,
                source_a,
                _create_reviewed(
                    client,
                    source_a,
                    marker="DeferredGuard",
                ),
            )
            with pytest.raises(
                DBAPIError,
                match="admission conversion is incoherent",
            ), database_admin.begin() as connection:
                no_conversion_operation_id = uuid4()
                _set_context(
                    connection,
                    user_id=source_a["auth"]["user"]["id"],
                    organization_id=source_a["auth"]["user"][
                        "organization_id"
                    ],
                    operation_id=no_conversion_operation_id,
                )
                _mark_accepted(
                    connection,
                    application_id=guard_candidate["id"],
                    offer_id=guard_candidate["offer"]["id"],
                    actor_user_id=source_a["auth"]["user"]["id"],
                    operation_id=no_conversion_operation_id,
                )
                connection.exec_driver_sql(
                    "SET CONSTRAINTS "
                    "admission_applications_conversion_coherence,"
                    "admission_offers_conversion_coherence IMMEDIATE"
                )

            second_child = _post(
                client,
                "/api/v1/children",
                source_a["headers"],
                {
                    "client_operation_id": str(uuid4()),
                    "family_id": source_a["family"]["id"],
                    "first_name": "Wrong",
                    "last_name": "Child",
                    "date_of_birth": "2023-03-01",
                },
            )
            with pytest.raises(
                DBAPIError,
                match="admission conversion is incoherent",
            ), database_admin.begin() as connection:
                wrong_child_operation_id = uuid4()
                _set_context(
                    connection,
                    user_id=source_a["auth"]["user"]["id"],
                    organization_id=source_a["auth"]["user"][
                        "organization_id"
                    ],
                    operation_id=wrong_child_operation_id,
                )
                _insert_conversion(
                    connection,
                    organization_id=source_a["auth"]["user"][
                        "organization_id"
                    ],
                    application_id=guard_candidate["id"],
                    offer_id=guard_candidate["offer"]["id"],
                    family_id=source_a["family"]["id"],
                    child_id=second_child["id"],
                    enrollment_id=source_a["enrollment"]["id"],
                    actor_user_id=source_a["auth"]["user"]["id"],
                    operation_id=wrong_child_operation_id,
                )
                _mark_accepted(
                    connection,
                    application_id=guard_candidate["id"],
                    offer_id=guard_candidate["offer"]["id"],
                    actor_user_id=source_a["auth"]["user"]["id"],
                    operation_id=wrong_child_operation_id,
                )
                connection.exec_driver_sql(
                    "SET CONSTRAINTS "
                    "admission_applications_conversion_coherence,"
                    "admission_offers_conversion_coherence,"
                    "admission_conversion_links_conversion_coherence IMMEDIATE"
                )
            with pytest.raises(
                DBAPIError,
                match="admission conversion is incoherent",
            ), database_admin.begin() as connection:
                nonpending_operation_id = uuid4()
                _set_context(
                    connection,
                    user_id=source_a["auth"]["user"]["id"],
                    organization_id=source_a["auth"]["user"][
                        "organization_id"
                    ],
                    operation_id=nonpending_operation_id,
                )
                connection.execute(
                    text(
                        "UPDATE public.enrollments SET status='active' "
                        "WHERE id=:enrollment_id"
                    ),
                    {"enrollment_id": source_a["enrollment"]["id"]},
                )
                _insert_conversion(
                    connection,
                    organization_id=source_a["auth"]["user"][
                        "organization_id"
                    ],
                    application_id=guard_candidate["id"],
                    offer_id=guard_candidate["offer"]["id"],
                    family_id=source_a["family"]["id"],
                    child_id=source_a["child"]["id"],
                    enrollment_id=source_a["enrollment"]["id"],
                    actor_user_id=source_a["auth"]["user"]["id"],
                    operation_id=nonpending_operation_id,
                )
                _mark_accepted(
                    connection,
                    application_id=guard_candidate["id"],
                    offer_id=guard_candidate["offer"]["id"],
                    actor_user_id=source_a["auth"]["user"]["id"],
                    operation_id=nonpending_operation_id,
                )
                connection.exec_driver_sql(
                    "SET CONSTRAINTS "
                    "admission_applications_conversion_coherence,"
                    "admission_offers_conversion_coherence,"
                    "admission_conversion_links_conversion_coherence IMMEDIATE"
                )
            with database_admin.connect() as connection:
                assert connection.scalar(
                    text(
                        "SELECT status FROM public.enrollments "
                        "WHERE id=:enrollment_id"
                    ),
                    {"enrollment_id": source_a["enrollment"]["id"]},
                ) == "pending"
                assert connection.scalar(
                    text(
                        "SELECT count(*) FROM "
                        "public.admission_conversion_links "
                        "WHERE application_id=:application_id"
                    ),
                    {"application_id": guard_candidate["id"]},
                ) == 0

        # M04: with admission history in two tenants and dependent rows, a
        # NOBYPASSRLS owner without tenant context must see the whole database,
        # refuse, and roll every temporary NO FORCE change back atomically.
        with database_admin.connect() as connection:
            populated_counts = _admission_counts(connection)
            assert connection.scalar(
                text(
                    "SELECT count(DISTINCT organization_id) "
                    "FROM public.admission_applications"
                )
            ) >= 2
            populated_security = _admission_security_snapshot(connection)
            populated_fingerprint = _schema_fingerprint(connection)
            role_permissions_before_refusal = list(
                connection.scalar(
                    text(
                        "SELECT permissions FROM public.roles "
                        "WHERE organization_id=:organization_id AND key='owner'"
                    ),
                    {
                        "organization_id": source_a["auth"]["user"][
                            "organization_id"
                        ]
                    },
                )
            )

        refused = _alembic("downgrade", PREVIOUS_REVISION)
        assert refused.returncode != 0
        assert (
            "0039 downgrade refused: admissions history or dependent events exist"
            in refused.stdout + refused.stderr
        )
        with database_admin.connect() as connection:
            assert connection.scalar(
                text("SELECT version_num FROM public.alembic_version")
            ) == CURRENT_REVISION
            assert _admission_counts(connection) == populated_counts
            assert _admission_security_snapshot(connection) == populated_security
            assert _schema_fingerprint(connection) == populated_fingerprint
            assert list(
                connection.scalar(
                    text(
                        "SELECT permissions FROM public.roles "
                        "WHERE organization_id=:organization_id AND key='owner'"
                    ),
                    {
                        "organization_id": source_a["auth"]["user"][
                            "organization_id"
                        ]
                    },
                )
            ) == role_permissions_before_refusal
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
