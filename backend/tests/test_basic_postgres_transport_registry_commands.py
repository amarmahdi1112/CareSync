"""Opt-in PostgreSQL 17 certification for the 0032 transport command boundary.

The integration test is intentionally inert unless an administrative URL for
an empty, disposable loopback cluster is supplied.  It creates and drops only
the ``caresync`` database and the three 0032 roles after first proving that
none of those names already exist.  Retained CareSync ports are rejected
before SQLAlchemy or psql can make a connection.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from threading import Event
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Connection, Engine, make_url
from sqlalchemy.exc import DBAPIError

from app.core.config import Settings
from app.db.session import Database

DISPOSABLE_URL_TEXT = os.getenv("BASIC_POSTGRES_TRANSPORT_COMMANDS_TEST_URL")
BACKEND_ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = BACKEND_ROOT / "scripts" / "bootstrap_basic_runtime_role.sql"
PSQL = Path(os.getenv("CARESYNC_PSQL", "/opt/homebrew/opt/postgresql@17/bin/psql"))

DATABASE_NAME = "caresync"
BASIC_ROLE = "caresync_basic_app"
EVIDENCE_ROLE = "caresync_transport_evidence_ingest"
COMMAND_OWNER_ROLE = "caresync_transport_command_owner"
PROTECTED_PORTS = {5432, 5433, 5434}
WRITER_SIGNATURE = "caresync_0032_execute_command(text,uuid,text,jsonb)"
EVIDENCE_COMMANDS = {"qualification_evidence", "vehicle_evidence"}

TRANSPORT_TABLES = (
    "transport_registry_command_receipts",
    "staff_driver_capability_versions",
    "staff_driver_qualification_versions",
    "staff_driver_authorization_decisions",
    "staff_driver_readiness_decisions",
    "transport_vehicles",
    "transport_vehicle_versions",
    "transport_vehicle_evidence_versions",
    "staff_driver_qualification_evidence_objects",
    "staff_driver_qualification_review_decisions",
    "transport_vehicle_evidence_review_decisions",
    "transport_vehicle_evidence_scan_facts",
)
AUTHORITY_FLAG_TABLES = (
    "transport_registry_command_receipts",
    "staff_driver_authorization_decisions",
    "staff_driver_readiness_decisions",
    "staff_driver_qualification_evidence_objects",
    "staff_driver_qualification_review_decisions",
    "transport_vehicle_evidence_review_decisions",
    "transport_vehicle_evidence_scan_facts",
)
WRITER_POLICY_TABLES = (*TRANSPORT_TABLES, "audit_events", "user_notifications")
COMMAND_OWNER_CONTEXT_TABLES = {
    "notification_push_subscriptions",
    "organization_memberships",
    "organizations",
    "roles",
    "user_notification_preferences",
    "users",
}
COMMAND_OWNER_ROW_LOCK_TABLES = {
    "users",
    "organizations",
    "organization_memberships",
    "roles",
    "staff_driver_capability_versions",
    "staff_driver_qualification_versions",
    "staff_driver_authorization_decisions",
    "transport_vehicles",
    "transport_vehicle_versions",
    "transport_vehicle_evidence_versions",
}
CONTEXT_LOCK_POLICY_SCOPES = {
    "users": ("id=nullifcurrent_setting'app.current_user_id'::text,true,''::text::uuid"),
    "organizations": (
        "id=nullifcurrent_setting'app.current_organization_id'::text,true,''::text::uuid"
    ),
    "organization_memberships": (
        "organization_id=nullifcurrent_setting"
        "'app.current_organization_id'::text,true,''::text::uuid"
    ),
    "roles": (
        "organization_id=nullifcurrent_setting"
        "'app.current_organization_id'::text,true,''::text::uuid"
    ),
}
COMMAND_OWNER_ARBITER_SELECT_COLUMNS = {
    "user_realtime_events": {"id"},
    "notification_deliveries": {"notification_id", "subscription_id"},
}
COMMAND_OWNER_INSERT_ONLY_TABLES = {
    "audit_events",
    "notification_deliveries",
    "realtime_events",
    "user_notifications",
    "user_realtime_events",
}
COMMAND_OWNER_SEQUENCES = {
    "realtime_events_sequence_id_seq",
    "user_realtime_events_sequence_id_seq",
}
GUARD_FUNCTIONS = (
    "caresync_0032_immutable_fact()",
    "caresync_0032_receipt_guard()",
    "caresync_0032_qualification_evidence_guard()",
    "caresync_0032_qualification_review_guard()",
    "caresync_0032_vehicle_review_guard()",
    "caresync_0032_vehicle_scan_guard()",
)
HARDENED_0031_GUARDS = (
    "caresync_0031_authorization_guard()",
    "caresync_0031_vehicle_version_guard()",
)


def _normalized_writer_policy(expression: str) -> str:
    compact = "".join(expression.lower().split()).replace('"', "")
    compact = compact.replace("::pg_catalog.name[]", "")
    compact = compact.replace("::pg_catalog.name", "")
    compact = compact.replace("::name[]", "").replace("::name", "")
    return compact.replace("(", "").replace(")", "")


def _postgres_function_definitions(
    connection: Connection,
    signatures: tuple[str, ...],
) -> dict[str, str]:
    rows = connection.execute(
        text(
            "SELECT function_value::text,pg_get_functiondef(function_value) "
            "FROM unnest(CAST(:functions AS regprocedure[])) AS function_value "
            "ORDER BY function_value::text"
        ),
        {"functions": [f"public.{signature}" for signature in signatures]},
    )
    return {signature.removeprefix("public."): definition for signature, definition in rows}


def _guard_disposable_url(value: str) -> URL:
    url = make_url(value)
    if not url.drivername.startswith("postgresql"):
        raise RuntimeError("0032 certification requires a PostgreSQL URL")
    if url.host not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError("0032 certification requires a loopback host")
    if url.port is None or url.port in PROTECTED_PORTS or not 1 <= url.port <= 65535:
        raise RuntimeError("0032 certification refuses retained or invalid ports")
    if url.database != "postgres":
        raise RuntimeError("0032 disposable URL must target the postgres database")
    if not url.username:
        raise RuntimeError("0032 disposable URL must include an administrative user")
    return url


ADMIN_CLUSTER_URL = _guard_disposable_url(DISPOSABLE_URL_TEXT) if DISPOSABLE_URL_TEXT else None


@pytest.mark.parametrize("port", [5432, 5433, 5434])
def test_0032_disposable_guard_rejects_retained_ports(port: int) -> None:
    with pytest.raises(RuntimeError, match="refuses retained"):
        _guard_disposable_url(f"postgresql+psycopg://postgres@127.0.0.1:{port}/postgres")


def test_0032_disposable_guard_rejects_remote_hosts() -> None:
    with pytest.raises(RuntimeError, match="loopback"):
        _guard_disposable_url("postgresql+psycopg://postgres@database.example.test:55493/postgres")


def test_0032_disposable_guard_accepts_fresh_loopback_cluster_shape() -> None:
    guarded = _guard_disposable_url("postgresql+psycopg://postgres@127.0.0.1:55493/postgres")
    assert guarded.host == "127.0.0.1"
    assert guarded.port == 55493


def _database_url(role: str, password: str | None = None) -> URL:
    assert ADMIN_CLUSTER_URL is not None
    return URL.create(
        "postgresql+psycopg",
        username=role,
        password=password,
        host=ADMIN_CLUSTER_URL.host,
        port=ADMIN_CLUSTER_URL.port,
        database=DATABASE_NAME,
    )


def _alembic(action: str, revision: str) -> subprocess.CompletedProcess[str]:
    assert ADMIN_CLUSTER_URL is not None
    environment = os.environ.copy()
    environment.update(
        {
            "ENVIRONMENT": "test",
            "DATABASE_TYPE": "postgres",
            "DATABASE_HOST": str(ADMIN_CLUSTER_URL.host),
            "DATABASE_PORT": str(ADMIN_CLUSTER_URL.port),
            "DATABASE_USER": str(ADMIN_CLUSTER_URL.username),
            "DATABASE_PASSWORD": str(ADMIN_CLUSTER_URL.password or ""),
            "DATABASE_NAME": DATABASE_NAME,
            "DATABASE_SSL": "false",
            "DATABASE_READ_ONLY": "false",
            "ENABLE_ADVANCED_ROUTES": "false",
        }
    )
    return subprocess.run(
        [sys.executable, "-m", "alembic", action, revision],
        cwd=BACKEND_ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


def _bootstrap() -> subprocess.CompletedProcess[str]:
    assert ADMIN_CLUSTER_URL is not None
    environment = os.environ.copy()
    if ADMIN_CLUSTER_URL.password:
        environment["PGPASSWORD"] = str(ADMIN_CLUSTER_URL.password)
    return subprocess.run(
        [
            str(PSQL),
            "-v",
            "ON_ERROR_STOP=1",
            "-h",
            str(ADMIN_CLUSTER_URL.host),
            "-p",
            str(ADMIN_CLUSTER_URL.port),
            "-U",
            str(ADMIN_CLUSTER_URL.username),
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


def _assert_policy_identity_tampering_fails_closed(
    database_admin: Engine,
    *,
    basic_password: str,
    evidence_password: str,
) -> None:
    policy = "staff_driver_capability_versions_0032_writer"
    table = "staff_driver_capability_versions"
    drifted = (
        "current_user='caresync_transport_command_owner' AND "
        "'caresync_basic_app' IS NOT NULL AND "
        "'caresync_transport_evidence_ingest' IS NOT NULL"
    )
    exact = (
        "current_user='caresync_transport_command_owner' AND "
        "session_user IN "
        "('caresync_basic_app','caresync_transport_evidence_ingest')"
    )
    with database_admin.begin() as connection:
        connection.execute(
            text(f"ALTER POLICY {policy} ON {table} USING ({drifted}) WITH CHECK ({drifted})")
        )

    assert ADMIN_CLUSTER_URL is not None
    runtime = Database(
        Settings(
            _env_file=None,
            environment="test",
            database_type="postgres",
            database_name=DATABASE_NAME,
            database_host=str(ADMIN_CLUSTER_URL.host),
            database_port=int(ADMIN_CLUSTER_URL.port or 0),
            database_user=BASIC_ROLE,
            database_password=basic_password,
            transport_evidence_ingest_password=evidence_password,
            database_read_only=False,
            enable_advanced_routes=False,
        )
    )
    try:
        with pytest.raises(RuntimeError, match="Partial or drifted 0032"):
            runtime.has_transport_registry_commands()
    finally:
        runtime.dispose()

    rejected = _bootstrap()
    assert rejected.returncode != 0
    assert "rls writer policy audit failed" in (rejected.stdout + rejected.stderr).lower()

    with database_admin.begin() as connection:
        connection.execute(
            text(f"ALTER POLICY {policy} ON {table} USING ({exact}) WITH CHECK ({exact})")
        )
    repaired = _bootstrap()
    assert repaired.returncode == 0, repaired.stdout + repaired.stderr


def _set_context(connection: Connection, *, user_id: UUID, organization_id: UUID) -> None:
    connection.execute(
        text("SELECT set_config('app.current_user_id',:value,true)"),
        {"value": str(user_id)},
    )
    connection.execute(
        text("SELECT set_config('app.current_organization_id',:value,true)"),
        {"value": str(organization_id)},
    )


def _request_digest(connection: Connection, payload: dict[str, object]) -> str:
    """Mirror the writer's privacy-minimized canonical request document."""

    return connection.scalar(
        text(
            "SELECT encode(sha256(convert_to((CAST(:payload AS jsonb)-ARRAY["
            "'result_id','version_id','evidence_object_id','review_id','scan_fact_id',"
            "'ciphertext_sha256','storage_reference','encryption_key_id','scanner_engine',"
            "'scanner_version','scanned_at'])::text,'UTF8')),'hex')"
        ),
        {"payload": json.dumps(payload)},
    )


def _command(
    connection: Connection,
    *,
    kind: str,
    operation_id: UUID,
    payload: dict[str, object],
    request_sha256: str | None = None,
) -> dict[str, object]:
    digest = request_sha256 or _request_digest(connection, payload)
    row = (
        connection.execute(
            text(
                "SELECT * FROM public.caresync_0032_execute_command("
                ":kind,:operation_id,:digest,CAST(:payload AS jsonb))"
            ),
            {
                "kind": kind,
                "operation_id": operation_id,
                "digest": digest,
                "payload": json.dumps(payload),
            },
        )
        .mappings()
        .one()
    )
    result = dict(row)
    assert result["operational_driver_ready"] is False
    assert result["dispatch_authorized"] is False
    return result


def _expect_command_error(
    engine: Engine,
    *,
    user_id: UUID,
    organization_id: UUID,
    kind: str,
    operation_id: UUID,
    payload: dict[str, object],
    marker: str,
    request_sha256: str | None = None,
) -> None:
    with pytest.raises(DBAPIError) as captured, engine.begin() as connection:
        _set_context(connection, user_id=user_id, organization_id=organization_id)
        _command(
            connection,
            kind=kind,
            operation_id=operation_id,
            payload=payload,
            request_sha256=request_sha256,
        )
    assert marker in str(captured.value).lower()


def _run_concurrent_command(
    engine: Engine,
    started: Event,
    *,
    user_id: UUID,
    organization_id: UUID,
    kind: str,
    operation_id: UUID,
    payload: dict[str, object],
) -> dict[str, object]:
    started.set()
    with engine.begin() as connection:
        _set_context(connection, user_id=user_id, organization_id=organization_id)
        return _command(
            connection,
            kind=kind,
            operation_id=operation_id,
            payload=payload,
        )


def _seed_identities(connection: Connection) -> dict[str, UUID]:
    values = {
        "org_a": uuid4(),
        "org_b": uuid4(),
        "manager_a": uuid4(),
        "staff_a": uuid4(),
        "manager_peer_a": uuid4(),
        "manager_b": uuid4(),
        "staff_b": uuid4(),
        "manager_role_a": uuid4(),
        "staff_role_a": uuid4(),
        "manager_role_b": uuid4(),
        "staff_role_b": uuid4(),
        "manager_membership_a": uuid4(),
        "staff_membership_a": uuid4(),
        "manager_peer_membership_a": uuid4(),
        "manager_membership_b": uuid4(),
        "staff_membership_b": uuid4(),
    }
    for suffix in ("a", "b"):
        connection.execute(
            text(
                "INSERT INTO organizations "
                "(id,name,status,verification_status,timezone,preferences) VALUES "
                "(:id,:name,'active','pending','America/Edmonton','{}'::json)"
            ),
            {"id": values[f"org_{suffix}"], "name": f"Transport Tenant {suffix}"},
        )
        for actor_kind in ("manager", "staff"):
            user_id = values[f"{actor_kind}_{suffix}"]
            connection.execute(
                text(
                    "INSERT INTO users "
                    "(id,email,password_hash,first_name,last_name,is_active,auth_version,"
                    "email_verified_at,email_verification_method) VALUES "
                    "(:id,:email,'unused','Transport',:last_name,true,1,now(),'test_fixture')"
                ),
                {
                    "id": user_id,
                    "email": f"transport-{actor_kind}-{suffix}-{uuid4().hex}@example.test",
                    "last_name": f"{actor_kind.title()}{suffix.upper()}",
                },
            )
        connection.execute(
            text(
                "INSERT INTO roles "
                "(id,organization_id,key,name,permissions,is_system) VALUES "
                "(:manager_role,:org,'transport_manager','Transport manager',"
                "'[\"transport:manage\"]'::json,true),"
                "(:staff_role,:org,'transport_staff','Transport staff','[]'::json,true)"
            ),
            {
                "manager_role": values[f"manager_role_{suffix}"],
                "staff_role": values[f"staff_role_{suffix}"],
                "org": values[f"org_{suffix}"],
            },
        )
        connection.execute(
            text(
                "INSERT INTO organization_memberships "
                "(id,organization_id,user_id,role_id,status,joined_at) VALUES "
                "(:manager_membership,:org,:manager,:manager_role,'active',now()),"
                "(:staff_membership,:org,:staff,:staff_role,'active',now())"
            ),
            {
                "manager_membership": values[f"manager_membership_{suffix}"],
                "org": values[f"org_{suffix}"],
                "manager": values[f"manager_{suffix}"],
                "manager_role": values[f"manager_role_{suffix}"],
                "staff_membership": values[f"staff_membership_{suffix}"],
                "staff": values[f"staff_{suffix}"],
                "staff_role": values[f"staff_role_{suffix}"],
            },
        )
    connection.execute(
        text(
            "INSERT INTO users "
            "(id,email,password_hash,first_name,last_name,is_active,auth_version,"
            "email_verified_at,email_verification_method) VALUES "
            "(:id,:email,'unused','Transport','Peer',true,1,now(),'test_fixture')"
        ),
        {
            "id": values["manager_peer_a"],
            "email": f"transport-manager-peer-a-{uuid4().hex}@example.test",
        },
    )
    connection.execute(
        text(
            "INSERT INTO organization_memberships "
            "(id,organization_id,user_id,role_id,status,joined_at) VALUES "
            "(:id,:org,:user_id,:role_id,'active',now())"
        ),
        {
            "id": values["manager_peer_membership_a"],
            "org": values["org_a"],
            "user_id": values["manager_peer_a"],
            "role_id": values["manager_role_a"],
        },
    )
    return values


def _seed_legacy_active_plate_drift(
    connection: Connection,
    identities: dict[str, UUID],
) -> dict[str, UUID]:
    vehicles = {
        "blank": uuid4(),
        "duplicate_a": uuid4(),
        "duplicate_b": uuid4(),
    }
    plates = {
        "blank": "--",
        "duplicate_a": "ABC 123",
        "duplicate_b": "a-b.c_123",
    }
    for key, vehicle_id in vehicles.items():
        connection.execute(
            text(
                "INSERT INTO transport_vehicles "
                "(id,organization_id,owner_kind,staff_owner_membership_id,"
                "created_by_user_id,created_at) VALUES "
                "(:id,:organization_id,'staff_personal',:membership_id,:actor_id,now())"
            ),
            {
                "id": vehicle_id,
                "organization_id": identities["org_a"],
                "membership_id": identities["manager_membership_a"],
                "actor_id": identities["manager_a"],
            },
        )
        connection.execute(
            text(
                "INSERT INTO transport_vehicle_versions "
                "(id,organization_id,vehicle_id,version_number,make,model,model_year,"
                "color,plate_token,plate_jurisdiction,passenger_capacity,"
                "child_passenger_capacity,wheelchair_accessible,effective_at,"
                "recorded_by_user_id,recorded_at) VALUES "
                "(:id,:organization_id,:vehicle_id,1,'Legacy','Fixture',2024,NULL,"
                ":plate,'CA-AB',7,6,false,now(),:actor_id,now())"
            ),
            {
                "id": uuid4(),
                "organization_id": identities["org_a"],
                "vehicle_id": vehicle_id,
                "plate": plates[key],
                "actor_id": identities["manager_a"],
            },
        )
    return vehicles


def _retire_legacy_vehicle(
    connection: Connection,
    *,
    vehicle_id: UUID,
    actor_id: UUID,
) -> None:
    connection.execute(
        text(
            "UPDATE transport_vehicles SET retired_at=now(),retired_by_user_id=:actor_id,"
            "retirement_reason_code='compatibility_preflight_fixture' WHERE id=:vehicle_id"
        ),
        {"actor_id": actor_id, "vehicle_id": vehicle_id},
    )


def _insert_direct_vehicle_version(
    connection: Connection,
    *,
    organization_id: UUID,
    vehicle_id: UUID,
    actor_id: UUID,
    plate_token: str,
    plate_jurisdiction: str,
) -> UUID:
    version_id = uuid4()
    connection.execute(
        text(
            "INSERT INTO transport_vehicle_versions "
            "(id,organization_id,vehicle_id,version_number,make,model,model_year,"
            "color,plate_token,plate_jurisdiction,passenger_capacity,"
            "child_passenger_capacity,wheelchair_accessible,effective_at,"
            "recorded_by_user_id,recorded_at) VALUES "
            "(:id,:organization_id,:vehicle_id,1,'Concurrency','Fixture',2024,NULL,"
            ":plate_token,:plate_jurisdiction,7,6,false,now(),:actor_id,now())"
        ),
        {
            "id": version_id,
            "organization_id": organization_id,
            "vehicle_id": vehicle_id,
            "plate_token": plate_token,
            "plate_jurisdiction": plate_jurisdiction,
            "actor_id": actor_id,
        },
    )
    return version_id


def _run_direct_vehicle_version(
    engine: Engine,
    started: Event,
    *,
    organization_id: UUID,
    vehicle_id: UUID,
    actor_id: UUID,
    plate_token: str,
    plate_jurisdiction: str,
) -> UUID:
    started.set()
    with engine.begin() as connection:
        return _insert_direct_vehicle_version(
            connection,
            organization_id=organization_id,
            vehicle_id=vehicle_id,
            actor_id=actor_id,
            plate_token=plate_token,
            plate_jurisdiction=plate_jurisdiction,
        )


def _driver_payload(membership_id: UUID, result_id: UUID) -> dict[str, object]:
    return {
        "result_id": str(result_id),
        "membership_id": str(membership_id),
        "status": "declared",
        "willing_to_drive": True,
        "licence_jurisdiction": "CA-AB",
        "licence_jurisdiction_other": "",
        "licence_class": "5",
        "vehicle_access": "personal_vehicle",
        "preferred_service_radius_km": 25,
    }


def _qualification_payload(
    actor_user_id: UUID,
    membership_id: UUID,
    result_id: UUID,
    evidence_id: UUID,
    *,
    marker: str,
    expiry_days: int = 365,
) -> dict[str, object]:
    today = date.today()
    return {
        "result_id": str(result_id),
        "evidence_object_id": str(evidence_id),
        "membership_id": str(membership_id),
        "qualification_type": "driver_licence",
        "jurisdiction": "CA-AB",
        "qualification_class": "5",
        "identifier_last4": "4821",
        "issue_date": (today - timedelta(days=30)).isoformat(),
        "expiry_date": (today + timedelta(days=expiry_days)).isoformat(),
        "original_filename": "driver-licence.pdf",
        "media_type": "application/pdf",
        "byte_size": 2048,
        "content_sha256": marker * 64,
        "ciphertext_sha256": chr(ord(marker) + 1) * 64,
        "storage_reference": (f"{actor_user_id.hex}/{membership_id.hex}/{uuid4().hex}/v1.enc"),
        "encryption_key_id": "transport-test-key-v1",
        "scanner_engine": "clamav",
        "scanner_version": "1.4.3/fixture-definitions",
        "scanned_at": datetime.now(UTC).isoformat(),
    }


def _vehicle_payload(membership_id: UUID, vehicle_id: UUID) -> dict[str, object]:
    return {
        "result_id": str(vehicle_id),
        "version_id": str(uuid4()),
        "owner_kind": "staff_personal",
        "staff_owner_membership_id": str(membership_id),
        "make": "Toyota",
        "model": "Sienna",
        "model_year": 2024,
        "color": "Blue",
        "plate_token": "PG0032",
        "plate_jurisdiction": "CA-AB",
        "passenger_capacity": 7,
        "child_passenger_capacity": 6,
        "wheelchair_accessible": False,
    }


def _vehicle_evidence_payload(
    actor_user_id: UUID,
    vehicle_id: UUID,
    result_id: UUID,
    *,
    evidence_type: str,
    marker: str,
    expiry_days: int = 335,
) -> dict[str, object]:
    today = date.today()
    return {
        "result_id": str(result_id),
        "scan_fact_id": str(uuid4()),
        "vehicle_id": str(vehicle_id),
        "evidence_type": evidence_type,
        "issue_date": (today - timedelta(days=30)).isoformat(),
        "expiry_date": (today + timedelta(days=expiry_days)).isoformat(),
        "original_filename": f"{evidence_type}.pdf",
        "media_type": "application/pdf",
        "byte_size": 4096,
        "content_sha256": marker * 64,
        "ciphertext_sha256": f"{(int(marker, 16) + 1) % 16:x}" * 64,
        "storage_reference": (f"{actor_user_id.hex}/{vehicle_id.hex}/{uuid4().hex}/v1.enc"),
        "encryption_key_id": "transport-test-key-v1",
        "scanner_engine": "clamav",
        "scanner_version": "1.4.3/fixture-definitions",
        "scanned_at": datetime.now(UTC).isoformat(),
    }


def _assert_role_and_function_boundary(connection: Connection) -> None:
    owner = connection.execute(
        text(
            "SELECT rolcanlogin,rolsuper,rolbypassrls,rolinherit,rolcreaterole,"
            "rolcreatedb,rolreplication FROM pg_roles WHERE rolname=:role"
        ),
        {"role": COMMAND_OWNER_ROLE},
    ).one()
    assert owner == (False, False, False, False, False, False, False)

    for role in (BASIC_ROLE, EVIDENCE_ROLE):
        runtime = connection.execute(
            text(
                "SELECT rolcanlogin,rolsuper,rolbypassrls,rolinherit,rolcreaterole,"
                "rolcreatedb,rolreplication FROM pg_roles WHERE rolname=:role"
            ),
            {"role": role},
        ).one()
        assert runtime == (True, False, False, False, False, False, False)

    role_configuration = {
        row.rolname: tuple(setting.replace(" ", "") for setting in (row.rolconfig or []))
        for row in connection.execute(
            text(
                "SELECT rolname,rolconfig FROM pg_roles WHERE rolname=ANY(CAST(:roles AS text[]))"
            ),
            {"roles": [BASIC_ROLE, EVIDENCE_ROLE, COMMAND_OWNER_ROLE]},
        )
    }
    assert role_configuration == {
        BASIC_ROLE: ("search_path=public,pg_catalog",),
        EVIDENCE_ROLE: ("search_path=public,pg_catalog",),
        COMMAND_OWNER_ROLE: (),
    }
    role_topology = connection.execute(
        text(
            "SELECT "
            "(SELECT count(*) FROM pg_auth_members AS edge "
            "JOIN pg_roles AS member ON member.oid=edge.member "
            "JOIN pg_roles AS granted ON granted.oid=edge.roleid "
            "WHERE member.rolname=ANY(CAST(:roles AS text[])) "
            "OR granted.rolname=ANY(CAST(:roles AS text[]))) AS memberships,"
            "(SELECT count(*) FROM pg_db_role_setting AS setting "
            "JOIN pg_roles AS role ON role.oid=setting.setrole "
            "WHERE role.rolname=ANY(CAST(:roles AS text[])) "
            "AND setting.setdatabase<>0) AS database_settings"
        ),
        {"roles": [BASIC_ROLE, EVIDENCE_ROLE, COMMAND_OWNER_ROLE]},
    ).one()
    assert role_topology == (0, 0)

    writer = connection.execute(
        text(
            "SELECT pg_get_userbyid(procedure.proowner),procedure.prosecdef,"
            "procedure.provolatile,procedure.proconfig,"
            "has_function_privilege(:basic,procedure.oid,'EXECUTE'),"
            "has_function_privilege(:ingest,procedure.oid,'EXECUTE'),"
            "EXISTS (SELECT 1 FROM aclexplode(COALESCE("
            "procedure.proacl,acldefault('f',procedure.proowner))) AS acl "
            "WHERE acl.grantee=0 AND acl.privilege_type='EXECUTE') "
            "FROM pg_proc AS procedure WHERE procedure.oid=to_regprocedure(:signature)"
        ),
        {
            "basic": BASIC_ROLE,
            "ingest": EVIDENCE_ROLE,
            "signature": f"public.{WRITER_SIGNATURE}",
        },
    ).one()
    assert writer[0] == COMMAND_OWNER_ROLE
    assert writer[1] is True
    assert writer[2] == "v"
    assert writer[3] is not None
    assert [item.replace(" ", "") for item in writer[3]] == ["search_path=pg_catalog,public"]
    assert writer[4:] == (True, True, False)
    writer_source = connection.scalar(
        text("SELECT prosrc FROM pg_proc WHERE oid=to_regprocedure(:signature)"),
        {"signature": f"public.{WRITER_SIGNATURE}"},
    )
    organization_lock = writer_source.index("caresync:transport:organization:")
    actor_lock = writer_source.index("FOR UPDATE OF actor,membership,organization_record")
    operation_lock = writer_source.index("requested_operation_id::text, 0")
    exact_retry_return = writer_source.index("RETURN QUERY SELECT existing.client_operation_id")
    clock_refresh = writer_source.index("now_value := pg_catalog.clock_timestamp()")
    assert organization_lock < actor_lock < operation_lock < exact_retry_return < clock_refresh

    ownership = connection.execute(
        text(
            "SELECT role.rolname,dependency.dbid,dependency.classid,dependency.objid "
            "FROM pg_roles AS role JOIN pg_shdepend AS dependency ON "
            "dependency.refclassid='pg_catalog.pg_authid'::regclass "
            "AND dependency.refobjid=role.oid AND dependency.deptype='o' "
            "WHERE role.rolname=ANY(CAST(:roles AS text[]))"
        ),
        {"roles": [BASIC_ROLE, EVIDENCE_ROLE, COMMAND_OWNER_ROLE]},
    ).all()
    assert {row.rolname for row in ownership} == {COMMAND_OWNER_ROLE}
    assert len(ownership) == 1
    owned = ownership[0]
    assert owned.dbid == connection.scalar(
        text("SELECT oid FROM pg_database WHERE datname=current_database()")
    )
    assert owned.classid == connection.scalar(text("SELECT 'pg_proc'::regclass::oid"))
    assert owned.objid == connection.scalar(
        text("SELECT to_regprocedure(:signature)::oid"),
        {"signature": f"public.{WRITER_SIGNATURE}"},
    )

    guard_acl = connection.execute(
        text(
            "SELECT expected.signature,"
            "COALESCE(has_function_privilege(:basic,procedure.oid,'EXECUTE'),false),"
            "COALESCE(has_function_privilege(:ingest,procedure.oid,'EXECUTE'),false),"
            "EXISTS (SELECT 1 FROM aclexplode(COALESCE("
            "procedure.proacl,acldefault('f',procedure.proowner))) AS acl "
            "WHERE acl.grantee=0 AND acl.privilege_type='EXECUTE') "
            "FROM unnest(CAST(:functions AS text[])) AS expected(signature) "
            "LEFT JOIN pg_proc AS procedure ON procedure.oid="
            "to_regprocedure('public.' || expected.signature)"
        ),
        {
            "basic": BASIC_ROLE,
            "ingest": EVIDENCE_ROLE,
            "functions": list(GUARD_FUNCTIONS),
        },
    ).all()
    assert len(guard_acl) == len(GUARD_FUNCTIONS)
    assert all(
        not basic_execute and not ingest_execute and not public_execute
        for _, basic_execute, ingest_execute, public_execute in guard_acl
    )

    repository_only = connection.execute(
        text(
            "SELECT "
            "has_database_privilege(:ingest,current_database(),'CONNECT'),"
            "has_database_privilege(:ingest,current_database(),'CREATE'),"
            "has_database_privilege(:ingest,current_database(),'TEMPORARY'),"
            "has_schema_privilege(:ingest,'public','USAGE'),"
            "has_schema_privilege(:ingest,'public','CREATE'),"
            "has_database_privilege(:owner,current_database(),'CREATE'),"
            "has_database_privilege(:owner,current_database(),'TEMPORARY'),"
            "has_schema_privilege(:owner,'public','USAGE'),"
            "has_schema_privilege(:owner,'public','CREATE')"
        ),
        {"ingest": EVIDENCE_ROLE, "owner": COMMAND_OWNER_ROLE},
    ).one()
    assert repository_only == (True, False, False, True, False, False, False, True, False)

    evidence_extra_function = connection.scalar(
        text(
            "SELECT EXISTS(SELECT 1 FROM pg_proc AS procedure "
            "JOIN pg_namespace AS namespace ON namespace.oid=procedure.pronamespace "
            "WHERE namespace.nspname !~ '^pg_' "
            "AND namespace.nspname<>'information_schema' "
            "AND procedure.oid<>to_regprocedure(:writer) "
            "AND has_function_privilege(:ingest,procedure.oid,'EXECUTE'))"
        ),
        {
            "ingest": EVIDENCE_ROLE,
            "writer": f"public.{WRITER_SIGNATURE}",
        },
    )
    assert evidence_extra_function is False

    evidence_table_privileges = connection.execute(
        text(
            "SELECT namespace.nspname,relation.relname,"
            "has_table_privilege(:ingest,relation.oid,'SELECT'),"
            "has_table_privilege(:ingest,relation.oid,'INSERT'),"
            "has_table_privilege(:ingest,relation.oid,'UPDATE'),"
            "has_table_privilege(:ingest,relation.oid,'DELETE'),"
            "has_table_privilege(:ingest,relation.oid,'TRUNCATE'),"
            "has_table_privilege(:ingest,relation.oid,'REFERENCES'),"
            "has_table_privilege(:ingest,relation.oid,'TRIGGER'),"
            "has_any_column_privilege(:ingest,relation.oid,'SELECT'),"
            "has_any_column_privilege(:ingest,relation.oid,'INSERT'),"
            "has_any_column_privilege(:ingest,relation.oid,'UPDATE'),"
            "has_any_column_privilege(:ingest,relation.oid,'REFERENCES') "
            "FROM pg_class AS relation JOIN pg_namespace AS namespace "
            "ON namespace.oid=relation.relnamespace "
            "WHERE namespace.nspname !~ '^pg_' "
            "AND namespace.nspname<>'information_schema' "
            "AND relation.relkind IN ('r','p')"
        ),
        {"ingest": EVIDENCE_ROLE},
    ).all()
    assert evidence_table_privileges
    assert all(not any(row[2:]) for row in evidence_table_privileges)

    evidence_sequence_privileges = connection.execute(
        text(
            "SELECT namespace.nspname,sequence.relname,"
            "has_sequence_privilege(:ingest,sequence.oid,'USAGE'),"
            "has_sequence_privilege(:ingest,sequence.oid,'SELECT'),"
            "has_sequence_privilege(:ingest,sequence.oid,'UPDATE') "
            "FROM pg_class AS sequence JOIN pg_namespace AS namespace "
            "ON namespace.oid=sequence.relnamespace "
            "WHERE namespace.nspname !~ '^pg_' "
            "AND namespace.nspname<>'information_schema' "
            "AND sequence.relkind='S'"
        ),
        {"ingest": EVIDENCE_ROLE},
    ).all()
    assert all(not any(row[2:]) for row in evidence_sequence_privileges)

    owner_table_privileges = connection.execute(
        text(
            "SELECT namespace.nspname,relation.relname,"
            "has_table_privilege(:owner,relation.oid,'SELECT') AS can_select,"
            "has_table_privilege(:owner,relation.oid,'INSERT') AS can_insert,"
            "has_table_privilege(:owner,relation.oid,'UPDATE') AS can_update,"
            "has_table_privilege(:owner,relation.oid,'DELETE') AS can_delete,"
            "has_table_privilege(:owner,relation.oid,'TRUNCATE') AS can_truncate,"
            "has_table_privilege(:owner,relation.oid,'REFERENCES') AS can_reference,"
            "has_table_privilege(:owner,relation.oid,'TRIGGER') AS can_trigger,"
            "has_any_column_privilege(:owner,relation.oid,'UPDATE') "
            "AS can_update_column FROM pg_class AS relation "
            "JOIN pg_namespace AS namespace ON namespace.oid=relation.relnamespace "
            "WHERE namespace.nspname !~ '^pg_' "
            "AND namespace.nspname<>'information_schema' "
            "AND relation.relkind IN ('r','p')"
        ),
        {"owner": COMMAND_OWNER_ROLE},
    ).all()
    for row in owner_table_privileges:
        expected_select = row.nspname == "public" and row.relname in (
            COMMAND_OWNER_CONTEXT_TABLES | set(TRANSPORT_TABLES)
        )
        expected_insert = row.nspname == "public" and row.relname in (
            COMMAND_OWNER_INSERT_ONLY_TABLES | set(TRANSPORT_TABLES)
        )
        assert bool(row.can_select) == expected_select
        assert bool(row.can_insert) == expected_insert
        assert row.can_update is False
        assert row.can_delete is False
        assert row.can_truncate is False
        assert row.can_reference is False
        assert row.can_trigger is False
        assert bool(row.can_update_column) == (
            row.nspname == "public" and row.relname in COMMAND_OWNER_ROW_LOCK_TABLES
        )

    owner_update_columns: dict[str, set[str]] = {}
    for table_name, column_name in connection.execute(
        text(
            "SELECT relation.relname,attribute.attname FROM pg_attribute AS attribute "
            "JOIN pg_class AS relation ON relation.oid=attribute.attrelid "
            "JOIN pg_namespace AS namespace ON namespace.oid=relation.relnamespace "
            "WHERE namespace.nspname='public' AND attribute.attnum>0 "
            "AND NOT attribute.attisdropped AND has_column_privilege("
            ":owner,attribute.attrelid,attribute.attnum,'UPDATE')"
        ),
        {"owner": COMMAND_OWNER_ROLE},
    ):
        owner_update_columns.setdefault(table_name, set()).add(column_name)
    expected_update_columns = {table: {"id"} for table in COMMAND_OWNER_ROW_LOCK_TABLES}
    expected_update_columns["transport_vehicles"].update(
        {"retired_at", "retired_by_user_id", "retirement_reason_code"}
    )
    assert owner_update_columns == expected_update_columns

    owner_arbiter_select_columns: dict[str, set[str]] = {}
    for table_name, column_name in connection.execute(
        text(
            "SELECT relation.relname,attribute.attname FROM pg_attribute AS attribute "
            "JOIN pg_class AS relation ON relation.oid=attribute.attrelid "
            "JOIN pg_namespace AS namespace ON namespace.oid=relation.relnamespace "
            "WHERE namespace.nspname='public' AND attribute.attnum>0 "
            "AND NOT attribute.attisdropped AND has_column_privilege("
            ":owner,attribute.attrelid,attribute.attnum,'SELECT') "
            "AND NOT has_table_privilege(:owner,attribute.attrelid,'SELECT')"
        ),
        {"owner": COMMAND_OWNER_ROLE},
    ):
        owner_arbiter_select_columns.setdefault(table_name, set()).add(column_name)
    assert owner_arbiter_select_columns == COMMAND_OWNER_ARBITER_SELECT_COLUMNS

    vehicle_update_columns = set(
        connection.execute(
            text(
                "SELECT attribute.attname FROM pg_attribute AS attribute "
                "WHERE attribute.attrelid='public.transport_vehicles'::regclass "
                "AND attribute.attnum>0 AND NOT attribute.attisdropped "
                "AND has_column_privilege(:owner,attribute.attrelid,attribute.attnum,'UPDATE')"
            ),
            {"owner": COMMAND_OWNER_ROLE},
        ).scalars()
    )
    assert vehicle_update_columns == {
        "id",
        "retired_at",
        "retired_by_user_id",
        "retirement_reason_code",
    }

    owner_sequence_privileges = connection.execute(
        text(
            "SELECT namespace.nspname,sequence.relname,"
            "has_sequence_privilege(:owner,sequence.oid,'USAGE') AS can_use,"
            "has_sequence_privilege(:owner,sequence.oid,'SELECT') AS can_select,"
            "has_sequence_privilege(:owner,sequence.oid,'UPDATE') AS can_update "
            "FROM pg_class AS sequence JOIN pg_namespace AS namespace "
            "ON namespace.oid=sequence.relnamespace "
            "WHERE namespace.nspname !~ '^pg_' "
            "AND namespace.nspname<>'information_schema' "
            "AND sequence.relkind='S'"
        ),
        {"owner": COMMAND_OWNER_ROLE},
    ).all()
    for row in owner_sequence_privileges:
        expected_usage = row.nspname == "public" and row.relname in COMMAND_OWNER_SEQUENCES
        assert bool(row.can_use) == expected_usage
        assert row.can_select is False
        assert row.can_update is False

    privileges = connection.execute(
        text(
            "SELECT role_name,table_name,"
            "has_table_privilege(role_name,to_regclass('public.' || table_name),'INSERT'),"
            "has_table_privilege(role_name,to_regclass('public.' || table_name),'UPDATE'),"
            "has_table_privilege(role_name,to_regclass('public.' || table_name),'DELETE') "
            "FROM unnest(CAST(:roles AS text[])) AS role_name "
            "CROSS JOIN unnest(CAST(:tables AS text[])) AS table_name"
        ),
        {
            "roles": [BASIC_ROLE, EVIDENCE_ROLE],
            "tables": list(TRANSPORT_TABLES),
        },
    ).all()
    assert len(privileges) == len(TRANSPORT_TABLES) * 2
    assert all(
        not insert and not update and not delete for _, _, insert, update, delete in privileges
    )

    hardened = connection.scalar(
        text(
            "SELECT count(*) FROM pg_class "
            "WHERE oid=ANY(CAST(:tables AS regclass[])) "
            "AND relrowsecurity AND relforcerowsecurity"
        ),
        {"tables": list(TRANSPORT_TABLES)},
    )
    assert hardened == len(TRANSPORT_TABLES)

    writer_policies = connection.execute(
        text(
            "SELECT relation.relname,policy.polname,policy.polcmd,"
            "policy.polpermissive,policy.polroles,"
            "pg_get_expr(policy.polqual,policy.polrelid) AS using_expression,"
            "pg_get_expr(policy.polwithcheck,policy.polrelid) AS check_expression "
            "FROM pg_policy AS policy JOIN pg_class AS relation "
            "ON relation.oid=policy.polrelid JOIN pg_namespace AS namespace "
            "ON namespace.oid=relation.relnamespace "
            "WHERE namespace.nspname='public' AND policy.polname LIKE '%\\_0032\\_writer' "
            "ESCAPE '\\'"
        )
    ).all()
    assert {(row.relname, row.polname) for row in writer_policies} == {
        (table, f"{table}_0032_writer") for table in WRITER_POLICY_TABLES
    }
    expected_writer_expression = (
        "current_user='caresync_transport_command_owner'and"
        "session_user=anyarray['caresync_basic_app',"
        "'caresync_transport_evidence_ingest']"
    )
    for policy in writer_policies:
        assert policy.polcmd == "*"
        assert policy.polpermissive is True
        assert tuple(policy.polroles) == (0,)
        assert _normalized_writer_policy(policy.using_expression) == expected_writer_expression
        assert _normalized_writer_policy(policy.check_expression) == expected_writer_expression

    context_lock_policies = connection.execute(
        text(
            "SELECT relation.relname,policy.polname,policy.polcmd,"
            "policy.polpermissive,policy.polroles,"
            "pg_get_expr(policy.polqual,policy.polrelid) AS using_expression,"
            "pg_get_expr(policy.polwithcheck,policy.polrelid) AS check_expression "
            "FROM pg_policy AS policy JOIN pg_class AS relation "
            "ON relation.oid=policy.polrelid JOIN pg_namespace AS namespace "
            "ON namespace.oid=relation.relnamespace "
            "WHERE namespace.nspname='public' "
            "AND relation.relname=ANY(CAST(:tables AS text[])) "
            "AND policy.polname IN (relation.relname || '_0032_lock',"
            "relation.relname || '_0032_lock_no_mutation')"
        ),
        {"tables": sorted(CONTEXT_LOCK_POLICY_SCOPES)},
    ).all()
    assert {(row.relname, row.polname) for row in context_lock_policies} == {
        (table, f"{table}_0032_lock") for table in CONTEXT_LOCK_POLICY_SCOPES
    } | {(table, f"{table}_0032_lock_no_mutation") for table in CONTEXT_LOCK_POLICY_SCOPES}
    for policy in context_lock_policies:
        scope = CONTEXT_LOCK_POLICY_SCOPES[policy.relname]
        lock_expression = f"{expected_writer_expression}and{scope}"
        assert policy.polcmd == "w"
        assert tuple(policy.polroles) == (0,)
        if policy.polname.endswith("_lock_no_mutation"):
            assert policy.polpermissive is False
            assert _normalized_writer_policy(policy.using_expression) == (
                "current_user<>'caresync_transport_command_owner'or" + lock_expression
            )
            assert _normalized_writer_policy(policy.check_expression) == (
                "current_user<>'caresync_transport_command_owner'"
            )
        else:
            assert policy.polpermissive is True
            assert _normalized_writer_policy(policy.using_expression) == lock_expression
            assert _normalized_writer_policy(policy.check_expression) == "false"


@pytest.mark.skipif(
    ADMIN_CLUSTER_URL is None,
    reason=(
        "BASIC_POSTGRES_TRANSPORT_COMMANDS_TEST_URL must name a fresh disposable "
        "loopback PostgreSQL 17 cluster"
    ),
)
def test_postgres_17_transport_commands_are_atomic_scoped_and_fail_closed() -> None:
    assert ADMIN_CLUSTER_URL is not None
    assert PSQL.is_file(), f"PostgreSQL 17 psql is unavailable at {PSQL}"
    cluster = create_engine(ADMIN_CLUSTER_URL, isolation_level="AUTOCOMMIT")
    database_admin: Engine | None = None
    basic: Engine | None = None
    evidence_ingest: Engine | None = None
    database_created = False
    role_namespace_owned = False
    basic_password = f"basic-{uuid4().hex}"
    evidence_password = f"ingest-{uuid4().hex}"
    try:
        with cluster.connect() as connection:
            version = int(connection.scalar(text("SHOW server_version_num")))
            assert 170000 <= version < 180000
            assert (
                connection.scalar(
                    text("SELECT 1 FROM pg_database WHERE datname=:name"),
                    {"name": DATABASE_NAME},
                )
                is None
            ), "The 0032 database name already exists; refusing destructive reuse"
            existing_roles = connection.scalar(
                text("SELECT count(*) FROM pg_roles WHERE rolname=ANY(CAST(:roles AS text[]))"),
                {
                    "roles": [BASIC_ROLE, EVIDENCE_ROLE, COMMAND_OWNER_ROLE],
                },
            )
            assert existing_roles == 0, "The 0032 role namespace must be fresh"
            role_namespace_owned = True
            connection.execute(text(f'CREATE DATABASE "{DATABASE_NAME}"'))
            database_created = True

        admin_database_url = ADMIN_CLUSTER_URL.set(database=DATABASE_NAME)
        database_admin = create_engine(admin_database_url)
        with database_admin.begin() as connection:
            connection.execute(text("REVOKE CREATE ON SCHEMA public FROM PUBLIC"))

        migration = _alembic("upgrade", "head")
        assert migration.returncode == 0, migration.stdout + migration.stderr
        with database_admin.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
                "0032_transport_commands"
            )
            fresh_0031_guard_definitions = _postgres_function_definitions(
                connection,
                HARDENED_0031_GUARDS,
            )

        empty_downgrade = _alembic("downgrade", "0031_driver_vehicle_registry")
        assert empty_downgrade.returncode == 0, empty_downgrade.stdout + empty_downgrade.stderr
        with database_admin.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
                "0031_driver_vehicle_registry"
            )
            assert (
                connection.scalar(
                    text(
                        "SELECT to_regprocedure("
                        "'public.caresync_0032_execute_command(text,uuid,text,jsonb)')"
                    )
                )
                is None
            )
        with database_admin.begin() as connection:
            for signature in HARDENED_0031_GUARDS:
                function_name = signature.removesuffix("()")
                connection.execute(
                    text(
                        f"CREATE OR REPLACE FUNCTION public.{function_name}() RETURNS trigger "
                        "LANGUAGE plpgsql SET search_path=pg_catalog,public AS $$ "
                        "BEGIN RETURN NEW; END $$"
                    )
                )
            assert (
                _postgres_function_definitions(
                    connection,
                    HARDENED_0031_GUARDS,
                )
                != fresh_0031_guard_definitions
            )
            compatibility_ids = _seed_identities(connection)
            legacy_vehicles = _seed_legacy_active_plate_drift(
                connection,
                compatibility_ids,
            )

        refused_blank_plate = _alembic("upgrade", "head")
        assert refused_blank_plate.returncode != 0
        assert "active vehicle has an empty normalized plate" in (
            refused_blank_plate.stdout + refused_blank_plate.stderr
        )
        with database_admin.begin() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
                "0031_driver_vehicle_registry"
            )
            assert (
                connection.scalar(
                    text("SELECT count(*) FROM transport_vehicles WHERE organization_id=:org"),
                    {"org": compatibility_ids["org_a"]},
                )
                == 3
            )
            assert (
                connection.scalar(
                    text("SELECT to_regclass('public.transport_registry_command_receipts')")
                )
                is None
            )
            _retire_legacy_vehicle(
                connection,
                vehicle_id=legacy_vehicles["blank"],
                actor_id=compatibility_ids["manager_a"],
            )

        refused_duplicate_plate = _alembic("upgrade", "head")
        assert refused_duplicate_plate.returncode != 0
        assert "duplicate normalized active vehicle plate" in (
            refused_duplicate_plate.stdout + refused_duplicate_plate.stderr
        )
        with database_admin.begin() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
                "0031_driver_vehicle_registry"
            )
            assert (
                connection.scalar(
                    text("SELECT count(*) FROM transport_vehicles WHERE organization_id=:org"),
                    {"org": compatibility_ids["org_a"]},
                )
                == 3
            )
            _retire_legacy_vehicle(
                connection,
                vehicle_id=legacy_vehicles["duplicate_a"],
                actor_id=compatibility_ids["manager_a"],
            )
        empty_reupgrade = _alembic("upgrade", "head")
        assert empty_reupgrade.returncode == 0, empty_reupgrade.stdout + empty_reupgrade.stderr
        with database_admin.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
                "0032_transport_commands"
            )
            assert (
                _postgres_function_definitions(connection, HARDENED_0031_GUARDS)
                == fresh_0031_guard_definitions
            )

        bootstrapped = _bootstrap()
        assert bootstrapped.returncode == 0, bootstrapped.stdout + bootstrapped.stderr
        with cluster.begin() as connection:
            connection.execute(text(f"ALTER ROLE {BASIC_ROLE} PASSWORD '{basic_password}'"))
            connection.execute(text(f"ALTER ROLE {EVIDENCE_ROLE} PASSWORD '{evidence_password}'"))

        basic = create_engine(_database_url(BASIC_ROLE, basic_password))
        evidence_ingest = create_engine(_database_url(EVIDENCE_ROLE, evidence_password))
        with evidence_ingest.connect() as connection:
            evidence_identity = connection.execute(
                text("SELECT current_user,session_user,current_setting('search_path')")
            ).one()
        assert evidence_identity[0:2] == (EVIDENCE_ROLE, EVIDENCE_ROLE)
        assert evidence_identity[2].replace(" ", "") == "public,pg_catalog"
        with database_admin.begin() as connection:
            ids = _seed_identities(connection)
            _assert_role_and_function_boundary(connection)

        with database_admin.connect() as connection:
            context_before = connection.execute(
                text(
                    "SELECT actor.id,actor.email,actor.is_active,actor.email_verified_at,"
                    "organization.id,organization.status,membership.id,membership.status,"
                    "role.id,role.permissions,"
                    "(SELECT count(*) FROM audit_events),"
                    "(SELECT count(*) FROM realtime_events) "
                    "FROM users AS actor "
                    "JOIN organization_memberships AS membership ON membership.user_id=actor.id "
                    "JOIN organizations AS organization "
                    "ON organization.id=membership.organization_id "
                    "JOIN roles AS role ON role.id=membership.role_id "
                    "WHERE actor.id=:user_id AND membership.id=:membership_id"
                ),
                {
                    "user_id": ids["manager_a"],
                    "membership_id": ids["manager_membership_a"],
                },
            ).one()
        with cluster.begin() as connection:
            connection.execute(text(f"GRANT {COMMAND_OWNER_ROLE} TO {BASIC_ROLE}"))
        try:
            with basic.begin() as connection:
                _set_context(
                    connection,
                    user_id=ids["manager_a"],
                    organization_id=ids["org_a"],
                )
                connection.execute(text(f"SET LOCAL ROLE {COMMAND_OWNER_ROLE}"))
                assert connection.execute(
                    text(
                        "SELECT current_user,session_user,actor.id "
                        "FROM users AS actor "
                        "JOIN organization_memberships AS membership "
                        "ON membership.user_id=actor.id "
                        "JOIN organizations AS organization_record "
                        "ON organization_record.id=membership.organization_id "
                        "JOIN roles AS actor_role ON actor_role.id=membership.role_id "
                        "WHERE actor.id=:user_id AND membership.id=:membership_id "
                        "FOR UPDATE OF actor,membership,organization_record,actor_role"
                    ),
                    {
                        "user_id": ids["manager_a"],
                        "membership_id": ids["manager_membership_a"],
                    },
                ).one() == (COMMAND_OWNER_ROLE, BASIC_ROLE, ids["manager_a"])
            with basic.begin() as connection:
                _set_context(
                    connection,
                    user_id=ids["manager_a"],
                    organization_id=ids["org_a"],
                )
                connection.execute(text(f"SET LOCAL ROLE {COMMAND_OWNER_ROLE}"))
                assert (
                    connection.execute(
                        text("UPDATE users SET id=id WHERE id=:id"),
                        {"id": ids["manager_a"]},
                    ).rowcount
                    == 1
                )
            for table_name, row_id in (
                ("organizations", ids["org_a"]),
                ("organization_memberships", ids["manager_membership_a"]),
                ("roles", ids["manager_role_a"]),
            ):
                with pytest.raises(DBAPIError), basic.begin() as connection:
                    _set_context(
                        connection,
                        user_id=ids["manager_a"],
                        organization_id=ids["org_a"],
                    )
                    connection.execute(text(f"SET LOCAL ROLE {COMMAND_OWNER_ROLE}"))
                    connection.execute(
                        text(f"UPDATE {table_name} SET id=id WHERE id=:id"),
                        {"id": row_id},
                    )
            with pytest.raises(DBAPIError), basic.begin() as connection:
                _set_context(
                    connection,
                    user_id=ids["manager_a"],
                    organization_id=ids["org_a"],
                )
                connection.execute(text(f"SET LOCAL ROLE {COMMAND_OWNER_ROLE}"))
                connection.execute(
                    text("UPDATE users SET id=:replacement WHERE id=:id"),
                    {"replacement": uuid4(), "id": ids["manager_a"]},
                )
        finally:
            with cluster.begin() as connection:
                connection.execute(text(f"REVOKE {COMMAND_OWNER_ROLE} FROM {BASIC_ROLE}"))
        with database_admin.connect() as connection:
            context_after = connection.execute(
                text(
                    "SELECT actor.id,actor.email,actor.is_active,actor.email_verified_at,"
                    "organization.id,organization.status,membership.id,membership.status,"
                    "role.id,role.permissions,"
                    "(SELECT count(*) FROM audit_events),"
                    "(SELECT count(*) FROM realtime_events) "
                    "FROM users AS actor "
                    "JOIN organization_memberships AS membership ON membership.user_id=actor.id "
                    "JOIN organizations AS organization "
                    "ON organization.id=membership.organization_id "
                    "JOIN roles AS role ON role.id=membership.role_id "
                    "WHERE actor.id=:user_id AND membership.id=:membership_id"
                ),
                {
                    "user_id": ids["manager_a"],
                    "membership_id": ids["manager_membership_a"],
                },
            ).one()
            assert context_after == context_before
            assert (
                connection.scalar(
                    text(
                        "SELECT count(*) FROM pg_auth_members AS edge "
                        "JOIN pg_roles AS member ON member.oid=edge.member "
                        "JOIN pg_roles AS granted ON granted.oid=edge.roleid "
                        "WHERE member.rolname=:basic AND granted.rolname=:owner"
                    ),
                    {"basic": BASIC_ROLE, "owner": COMMAND_OWNER_ROLE},
                )
                == 0
            )

        held_organization_connection = database_admin.connect()
        held_organization_transaction = held_organization_connection.begin()
        try:
            held_organization_connection.execute(
                text(
                    "SELECT pg_advisory_xact_lock(hashtextextended("
                    "'caresync:transport:organization:' || CAST(:org AS text),0))"
                ),
                {"org": ids["org_a"]},
            )
            manager_started = Event()
            peer_started = Event()
            with ThreadPoolExecutor(max_workers=2) as executor:
                manager_future = executor.submit(
                    _run_concurrent_command,
                    basic,
                    manager_started,
                    user_id=ids["manager_a"],
                    organization_id=ids["org_a"],
                    kind="driver_declaration",
                    operation_id=uuid4(),
                    payload=_driver_payload(ids["manager_membership_a"], uuid4()),
                )
                peer_future = executor.submit(
                    _run_concurrent_command,
                    basic,
                    peer_started,
                    user_id=ids["manager_peer_a"],
                    organization_id=ids["org_a"],
                    kind="driver_declaration",
                    operation_id=uuid4(),
                    payload=_driver_payload(ids["manager_peer_membership_a"], uuid4()),
                )
                assert manager_started.wait(timeout=2)
                assert peer_started.wait(timeout=2)
                with pytest.raises(FutureTimeoutError):
                    manager_future.result(timeout=0.25)
                with pytest.raises(FutureTimeoutError):
                    peer_future.result(timeout=0.25)
                release_time = held_organization_connection.scalar(text("SELECT clock_timestamp()"))
                held_organization_transaction.commit()
                manager_result = manager_future.result(timeout=5)
                peer_result = peer_future.result(timeout=5)
            assert manager_result["committed_at"] >= release_time
            assert peer_result["committed_at"] >= release_time
        finally:
            if held_organization_transaction.is_active:
                held_organization_transaction.rollback()
            held_organization_connection.close()

        race_vehicle_a = uuid4()
        race_vehicle_b = uuid4()
        with database_admin.begin() as connection:
            for race_vehicle in (race_vehicle_a, race_vehicle_b):
                connection.execute(
                    text(
                        "INSERT INTO transport_vehicles "
                        "(id,organization_id,owner_kind,staff_owner_membership_id,"
                        "created_by_user_id,created_at) VALUES "
                        "(:id,:organization_id,'organization',NULL,:actor_id,now())"
                    ),
                    {
                        "id": race_vehicle,
                        "organization_id": ids["org_a"],
                        "actor_id": ids["manager_a"],
                    },
                )
        held_plate_connection = database_admin.connect()
        held_plate_transaction = held_plate_connection.begin()
        try:
            _insert_direct_vehicle_version(
                held_plate_connection,
                organization_id=ids["org_a"],
                vehicle_id=race_vehicle_a,
                actor_id=ids["manager_a"],
                plate_token="Race 321",
                plate_jurisdiction="CA AB",
            )
            plate_started = Event()
            with ThreadPoolExecutor(max_workers=1) as executor:
                plate_future = executor.submit(
                    _run_direct_vehicle_version,
                    database_admin,
                    plate_started,
                    organization_id=ids["org_a"],
                    vehicle_id=race_vehicle_b,
                    actor_id=ids["manager_a"],
                    plate_token="r-a.c_e321",
                    plate_jurisdiction="ca-ab",
                )
                assert plate_started.wait(timeout=2)
                with pytest.raises(FutureTimeoutError):
                    plate_future.result(timeout=0.25)
                held_plate_transaction.commit()
                with pytest.raises(DBAPIError) as plate_conflict:
                    plate_future.result(timeout=5)
            assert "transport_vehicle_plate_conflict" in str(plate_conflict.value).lower()
        finally:
            if held_plate_transaction.is_active:
                held_plate_transaction.rollback()
            held_plate_connection.close()
        with database_admin.begin() as connection:
            _retire_legacy_vehicle(
                connection,
                vehicle_id=race_vehicle_a,
                actor_id=ids["manager_a"],
            )
            released_plate_version = _insert_direct_vehicle_version(
                connection,
                organization_id=ids["org_a"],
                vehicle_id=race_vehicle_b,
                actor_id=ids["manager_a"],
                plate_token="r-a.c_e321",
                plate_jurisdiction="ca-ab",
            )
            assert (
                connection.scalar(
                    text("SELECT count(*) FROM transport_vehicle_versions WHERE id=:id"),
                    {"id": released_plate_version},
                )
                == 1
            )

        driver_result_id = uuid4()
        driver_operation = uuid4()
        driver_payload = _driver_payload(ids["staff_membership_a"], driver_result_id)
        with basic.begin() as connection:
            _set_context(connection, user_id=ids["staff_a"], organization_id=ids["org_a"])
            first = _command(
                connection,
                kind="driver_declaration",
                operation_id=driver_operation,
                payload=driver_payload,
            )
        assert first["result_id"] == driver_result_id
        assert first["exact_retry"] is False

        with basic.begin() as connection:
            _set_context(connection, user_id=ids["staff_a"], organization_id=ids["org_a"])
            retried = _command(
                connection,
                kind="driver_declaration",
                operation_id=driver_operation,
                payload=driver_payload,
            )
        assert retried["result_id"] == first["result_id"]
        assert retried["committed_at"] == first["committed_at"]
        assert retried["exact_retry"] is True

        changed_driver_payload = {**driver_payload, "willing_to_drive": False}
        _expect_command_error(
            basic,
            user_id=ids["staff_a"],
            organization_id=ids["org_a"],
            kind="driver_declaration",
            operation_id=driver_operation,
            payload=changed_driver_payload,
            marker="transport_operation_reused",
        )
        _expect_command_error(
            basic,
            user_id=ids["staff_a"],
            organization_id=ids["org_a"],
            kind="driver_declaration",
            operation_id=driver_operation,
            payload=driver_payload,
            request_sha256="f" * 64,
            marker="transport_request_digest_mismatch",
        )

        foreign_capability_id = uuid4()
        with basic.begin() as connection:
            _set_context(connection, user_id=ids["staff_b"], organization_id=ids["org_b"])
            _command(
                connection,
                kind="driver_declaration",
                operation_id=uuid4(),
                payload=_driver_payload(ids["staff_membership_b"], foreign_capability_id),
            )
        _expect_command_error(
            basic,
            user_id=ids["manager_a"],
            organization_id=ids["org_a"],
            kind="driver_authorization",
            operation_id=uuid4(),
            payload={
                "result_id": str(uuid4()),
                "membership_id": str(ids["staff_membership_a"]),
                "capability_version_id": str(foreign_capability_id),
                "qualification_version_ids": [],
                "decision": "needs_review",
                "reason_code": "foreign_capability_must_fail",
                "authorization_valid_from": None,
                "authorization_valid_until": None,
            },
            marker="transport_authorization_capability_mismatch",
        )

        qualification_id = uuid4()
        qualification_evidence_id = uuid4()
        qualification_payload = _qualification_payload(
            ids["staff_a"],
            ids["staff_membership_a"],
            qualification_id,
            qualification_evidence_id,
            marker="a",
            expiry_days=20,
        )
        _expect_command_error(
            basic,
            user_id=ids["staff_a"],
            organization_id=ids["org_a"],
            kind="qualification_evidence",
            operation_id=uuid4(),
            payload=qualification_payload,
            marker="transport_command_forbidden",
        )
        _expect_command_error(
            evidence_ingest,
            user_id=ids["staff_a"],
            organization_id=ids["org_a"],
            kind="driver_declaration",
            operation_id=uuid4(),
            payload=_driver_payload(ids["staff_membership_a"], uuid4()),
            marker="transport_command_forbidden",
        )
        qualification_operation = uuid4()
        with evidence_ingest.begin() as connection:
            _set_context(connection, user_id=ids["staff_a"], organization_id=ids["org_a"])
            qualification_result = _command(
                connection,
                kind="qualification_evidence",
                operation_id=qualification_operation,
                payload=qualification_payload,
            )
        assert qualification_result["result_id"] == qualification_id

        retry_qualification_id = uuid4()
        retry_evidence_object_id = uuid4()
        qualification_retry_payload = {
            **qualification_payload,
            "result_id": str(retry_qualification_id),
            "evidence_object_id": str(retry_evidence_object_id),
            "ciphertext_sha256": "9" * 64,
            "storage_reference": (
                f"{ids['staff_a'].hex}/{ids['staff_membership_a'].hex}/{uuid4().hex}/v1.enc"
            ),
            "encryption_key_id": "transport-test-key-v2",
            "scanner_engine": "clamdscan",
            "scanner_version": "1.4.3/retry-definitions",
            "scanned_at": (datetime.now(UTC) + timedelta(seconds=5)).isoformat(),
        }
        with evidence_ingest.begin() as connection:
            _set_context(connection, user_id=ids["staff_a"], organization_id=ids["org_a"])
            qualification_retry = _command(
                connection,
                kind="qualification_evidence",
                operation_id=qualification_operation,
                payload=qualification_retry_payload,
            )
        assert qualification_retry["exact_retry"] is True
        assert qualification_retry["result_id"] == qualification_result["result_id"]
        assert qualification_retry["committed_at"] == qualification_result["committed_at"]
        with database_admin.connect() as connection:
            assert (
                connection.scalar(
                    text(
                        "SELECT count(*) FROM staff_driver_qualification_versions "
                        "WHERE id IN (:original,:retry)"
                    ),
                    {"original": qualification_id, "retry": retry_qualification_id},
                )
                == 1
            )
            assert (
                connection.scalar(
                    text(
                        "SELECT count(*) FROM staff_driver_qualification_evidence_objects "
                        "WHERE id IN (:original,:retry)"
                    ),
                    {"original": qualification_evidence_id, "retry": retry_evidence_object_id},
                )
                == 1
            )

        changed_qualification_payload = {
            **qualification_retry_payload,
            "result_id": str(uuid4()),
            "evidence_object_id": str(uuid4()),
            "content_sha256": "e" * 64,
            "ciphertext_sha256": "f" * 64,
            "storage_reference": (
                f"{ids['staff_a'].hex}/{ids['staff_membership_a'].hex}/{uuid4().hex}/v1.enc"
            ),
        }
        _expect_command_error(
            evidence_ingest,
            user_id=ids["staff_a"],
            organization_id=ids["org_a"],
            kind="qualification_evidence",
            operation_id=qualification_operation,
            payload=changed_qualification_payload,
            marker="transport_operation_reused",
        )

        review_result_id = uuid4()
        qualification_review_payload = {
            "result_id": str(review_result_id),
            "review_id": str(uuid4()),
            "membership_id": str(ids["staff_membership_a"]),
            "source_qualification_version_id": str(qualification_id),
            "decision": "verified",
            "reason_code": "independent_evidence_review",
        }
        _expect_command_error(
            basic,
            user_id=ids["staff_a"],
            organization_id=ids["org_a"],
            kind="qualification_review",
            operation_id=uuid4(),
            payload=qualification_review_payload,
            marker="transport_command_forbidden",
        )
        with basic.begin() as connection:
            _set_context(
                connection,
                user_id=ids["manager_a"],
                organization_id=ids["org_a"],
            )
            qualification_review = _command(
                connection,
                kind="qualification_review",
                operation_id=uuid4(),
                payload=qualification_review_payload,
            )
        assert qualification_review["result_id"] == review_result_id

        manager_qualification_id = uuid4()
        manager_qualification_payload = _qualification_payload(
            ids["manager_a"],
            ids["manager_membership_a"],
            manager_qualification_id,
            uuid4(),
            marker="c",
        )
        with evidence_ingest.begin() as connection:
            _set_context(
                connection,
                user_id=ids["manager_a"],
                organization_id=ids["org_a"],
            )
            _command(
                connection,
                kind="qualification_evidence",
                operation_id=uuid4(),
                payload=manager_qualification_payload,
            )
        self_review_payload = {
            "result_id": str(uuid4()),
            "review_id": str(uuid4()),
            "membership_id": str(ids["manager_membership_a"]),
            "source_qualification_version_id": str(manager_qualification_id),
            "decision": "verified",
            "reason_code": "self_review_must_fail",
        }
        _expect_command_error(
            basic,
            user_id=ids["manager_a"],
            organization_id=ids["org_a"],
            kind="qualification_review",
            operation_id=uuid4(),
            payload=self_review_payload,
            marker="transport_independent_review_required",
        )

        authorization_id = uuid4()
        authorization_payload = {
            "result_id": str(authorization_id),
            "membership_id": str(ids["staff_membership_a"]),
            "capability_version_id": str(driver_result_id),
            "qualification_version_ids": [str(review_result_id)],
            "decision": "authorized",
            "reason_code": "independent_qualification_verified",
            "authorization_valid_from": (datetime.now(UTC) + timedelta(minutes=1)).isoformat(),
            "authorization_valid_until": (datetime.now(UTC) + timedelta(days=10)).isoformat(),
        }
        with basic.begin() as connection:
            _set_context(
                connection,
                user_id=ids["manager_a"],
                organization_id=ids["org_a"],
            )
            authorization_result = _command(
                connection,
                kind="driver_authorization",
                operation_id=uuid4(),
                payload=authorization_payload,
            )
        assert authorization_result["result_id"] == authorization_id

        vehicle_id = uuid4()
        vehicle_payload = _vehicle_payload(ids["staff_membership_a"], vehicle_id)
        with basic.begin() as connection:
            _set_context(connection, user_id=ids["staff_a"], organization_id=ids["org_a"])
            vehicle_result = _command(
                connection,
                kind="vehicle_create",
                operation_id=uuid4(),
                payload=vehicle_payload,
            )
        assert vehicle_result["result_id"] == vehicle_id

        verified_vehicle_evidence_ids: list[UUID] = []
        submitted_vehicle_evidence: list[dict[str, object]] = []
        for evidence_type, marker in (("registration", "d"), ("insurance", "f")):
            source_evidence_id = uuid4()
            vehicle_evidence_payload = _vehicle_evidence_payload(
                ids["staff_a"],
                vehicle_id,
                source_evidence_id,
                evidence_type=evidence_type,
                marker=marker,
                expiry_days=20 if evidence_type == "registration" else 335,
            )
            with evidence_ingest.begin() as connection:
                _set_context(
                    connection,
                    user_id=ids["staff_a"],
                    organization_id=ids["org_a"],
                )
                source_result = _command(
                    connection,
                    kind="vehicle_evidence",
                    operation_id=uuid4(),
                    payload=vehicle_evidence_payload,
                )
            assert source_result["result_id"] == source_evidence_id
            submitted_vehicle_evidence.append(vehicle_evidence_payload)

            reviewed_evidence_id = uuid4()
            vehicle_review_payload = {
                "result_id": str(reviewed_evidence_id),
                "review_id": str(uuid4()),
                "vehicle_id": str(vehicle_id),
                "source_evidence_version_id": str(source_evidence_id),
                "decision": "verified",
                "reason_code": "independent_clean_scan_review",
            }
            with basic.begin() as connection:
                _set_context(
                    connection,
                    user_id=ids["manager_a"],
                    organization_id=ids["org_a"],
                )
                reviewed = _command(
                    connection,
                    kind="vehicle_evidence_review",
                    operation_id=uuid4(),
                    payload=vehicle_review_payload,
                )
                assert reviewed["result_id"] == reviewed_evidence_id
                verified_vehicle_evidence_ids.append(reviewed_evidence_id)

        locked_registry_rows = (
            ("staff_driver_capability_versions", driver_result_id),
            ("staff_driver_qualification_versions", review_result_id),
            ("staff_driver_authorization_decisions", authorization_id),
            ("transport_vehicles", vehicle_id),
            (
                "transport_vehicle_versions",
                UUID(str(vehicle_payload["version_id"])),
            ),
            (
                "transport_vehicle_evidence_versions",
                verified_vehicle_evidence_ids[0],
            ),
        )
        with database_admin.connect() as connection:
            registry_effects_before = connection.execute(
                text(
                    "SELECT (SELECT count(*) FROM audit_events),"
                    "(SELECT count(*) FROM realtime_events),"
                    "(SELECT count(*) FROM user_notifications)"
                )
            ).one()
        with cluster.begin() as connection:
            connection.execute(text(f"GRANT {COMMAND_OWNER_ROLE} TO {BASIC_ROLE}"))
        try:
            for table_name, row_id in locked_registry_rows:
                with pytest.raises(DBAPIError), basic.begin() as connection:
                    _set_context(
                        connection,
                        user_id=ids["manager_a"],
                        organization_id=ids["org_a"],
                    )
                    connection.execute(text(f"SET LOCAL ROLE {COMMAND_OWNER_ROLE}"))
                    connection.execute(
                        text(f"UPDATE {table_name} SET id=id WHERE id=:id"),
                        {"id": row_id},
                    )
        finally:
            with cluster.begin() as connection:
                connection.execute(text(f"REVOKE {COMMAND_OWNER_ROLE} FROM {BASIC_ROLE}"))
        with database_admin.connect() as connection:
            assert (
                connection.execute(
                    text(
                        "SELECT (SELECT count(*) FROM audit_events),"
                        "(SELECT count(*) FROM realtime_events),"
                        "(SELECT count(*) FROM user_notifications)"
                    )
                ).one()
                == registry_effects_before
            )
            for table_name, row_id in locked_registry_rows:
                assert (
                    connection.scalar(
                        text(f"SELECT count(*) FROM {table_name} WHERE id=:id"),
                        {"id": row_id},
                    )
                    == 1
                )

        unrelated_unique_readiness_id = uuid4()
        unrelated_unique_operation_id = uuid4()
        with database_admin.begin() as connection:
            connection.execute(
                text(
                    "CREATE FUNCTION public.caresync_test_0032_notification_unique_abort() "
                    "RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN "
                    "RAISE EXCEPTION 'test_unrelated_notification_unique' USING "
                    "ERRCODE='23505',CONSTRAINT='caresync_test_unrelated_notification_unique'; "
                    "END $$"
                )
            )
            connection.execute(
                text(
                    "CREATE TRIGGER aaa_caresync_test_0032_notification_unique_abort "
                    "BEFORE INSERT ON user_notifications FOR EACH ROW EXECUTE FUNCTION "
                    "public.caresync_test_0032_notification_unique_abort()"
                )
            )
        _expect_command_error(
            basic,
            user_id=ids["manager_a"],
            organization_id=ids["org_a"],
            kind="readiness_evaluation",
            operation_id=unrelated_unique_operation_id,
            payload={
                "result_id": str(unrelated_unique_readiness_id),
                "membership_id": str(ids["staff_membership_a"]),
                "vehicle_id": str(vehicle_id),
            },
            marker="test_unrelated_notification_unique",
        )
        with database_admin.begin() as connection:
            assert (
                connection.scalar(
                    text("SELECT count(*) FROM staff_driver_readiness_decisions WHERE id=:id"),
                    {"id": unrelated_unique_readiness_id},
                )
                == 0
            )
            assert (
                connection.scalar(
                    text(
                        "SELECT count(*) FROM transport_registry_command_receipts "
                        "WHERE client_operation_id=:id"
                    ),
                    {"id": unrelated_unique_operation_id},
                )
                == 0
            )
            connection.execute(
                text(
                    "DROP TRIGGER aaa_caresync_test_0032_notification_unique_abort "
                    "ON user_notifications"
                )
            )
            connection.execute(
                text("DROP FUNCTION public.caresync_test_0032_notification_unique_abort()")
            )

        staff_subscription_id = uuid4()
        with database_admin.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO notification_push_subscriptions("
                    "id,user_id,organization_id,device_id,transport,platform,"
                    "delivery_address,address_digest,status) VALUES ("
                    ":id,:user_id,:organization_id,:device_id,'expo','android',"
                    ":delivery_address,:address_digest,'active')"
                ),
                {
                    "id": staff_subscription_id,
                    "user_id": ids["staff_a"],
                    "organization_id": ids["org_a"],
                    "device_id": uuid4(),
                    "delivery_address": f"ExpoPushToken[transport-{uuid4().hex}]",
                    "address_digest": uuid4().hex + uuid4().hex,
                },
            )

        readiness_id = uuid4()
        readiness_operation = uuid4()
        readiness_payload = {
            "result_id": str(readiness_id),
            "membership_id": str(ids["staff_membership_a"]),
            "vehicle_id": str(vehicle_id),
        }
        with basic.begin() as connection:
            _set_context(
                connection,
                user_id=ids["manager_a"],
                organization_id=ids["org_a"],
            )
            readiness = _command(
                connection,
                kind="readiness_evaluation",
                operation_id=readiness_operation,
                payload=readiness_payload,
            )
        assert readiness["result_id"] == readiness_id

        with basic.begin() as connection:
            _set_context(
                connection,
                user_id=ids["manager_a"],
                organization_id=ids["org_a"],
            )
            readiness_retry = _command(
                connection,
                kind="readiness_evaluation",
                operation_id=readiness_operation,
                payload={**readiness_payload, "result_id": str(uuid4())},
            )
        assert readiness_retry["exact_retry"] is True
        assert readiness_retry["result_id"] == readiness_id
        assert readiness_retry["committed_at"] == readiness["committed_at"]

        with database_admin.connect() as connection:
            readiness_fact = connection.execute(
                text(
                    "SELECT reason_codes,vehicle_evidence_version_ids FROM "
                    "staff_driver_readiness_decisions WHERE id=:id"
                ),
                {"id": readiness_id},
            ).one()
            assert "driver_licence_expiring_soon" in readiness_fact.reason_codes
            assert "vehicle_evidence_expiring_soon" in readiness_fact.reason_codes
            assert set(readiness_fact.vehicle_evidence_version_ids) == {
                str(value) for value in verified_vehicle_evidence_ids
            }
            notifications = (
                connection.execute(
                    text(
                        "SELECT id,user_id,event_key,category,severity,action_path,"
                        "action_entity_type,action_entity_id FROM user_notifications "
                        "WHERE organization_id=:organization_id AND ("
                        "event_key LIKE 'driver-licence-expiry:%' OR "
                        "event_key LIKE 'vehicle-evidence-expiry:%')"
                    ),
                    {"organization_id": ids["org_a"]},
                )
                .mappings()
                .all()
            )
            assert len(notifications) == 6
            assert {row["user_id"] for row in notifications} == {
                ids["staff_a"],
                ids["manager_a"],
                ids["manager_peer_a"],
            }
            assert {row["category"] for row in notifications} == {"credential"}
            assert {row["severity"] for row in notifications} == {"warning"}
            assert {row["action_path"] for row in notifications} == {"/transport-registry"}
            assert {row["action_entity_type"] for row in notifications} == {"transport_registry"}
            assert {row["action_entity_id"] for row in notifications} == {readiness_id}
            notification_ids = {row["id"] for row in notifications}
            private_events = (
                connection.execute(
                    text(
                        "SELECT id,user_id,event_type,entity_type,entity_id,payload "
                        "FROM user_realtime_events WHERE id=ANY(CAST(:ids AS uuid[]))"
                    ),
                    {"ids": list(notification_ids)},
                )
                .mappings()
                .all()
            )
            assert len(private_events) == len(notifications)
            assert {row["event_type"] for row in private_events} == {"notification.created"}
            assert {row["entity_type"] for row in private_events} == {"notification"}
            assert {row["entity_id"] for row in private_events} == notification_ids
            assert {json.dumps(row["payload"], sort_keys=True) for row in private_events} == {
                json.dumps({"source": "notification_ledger"}, sort_keys=True)
            }
            deliveries = (
                connection.execute(
                    text(
                        "SELECT notification_id,subscription_id,status,payload "
                        "FROM notification_deliveries "
                        "WHERE notification_id=ANY(CAST(:ids AS uuid[]))"
                    ),
                    {"ids": list(notification_ids)},
                )
                .mappings()
                .all()
            )
            assert len(deliveries) == 2
            assert {row["subscription_id"] for row in deliveries} == {staff_subscription_id}
            assert {row["status"] for row in deliveries} == {"pending"}
            assert all(
                row["payload"]
                == {
                    "type": "notification",
                    "notification_id": str(row["notification_id"]),
                    "category": "credential",
                    "severity": "warning",
                }
                for row in deliveries
            )

        held_readiness_connection = basic.connect()
        held_readiness_transaction = held_readiness_connection.begin()
        revocation_future = None
        try:
            _set_context(
                held_readiness_connection,
                user_id=ids["manager_a"],
                organization_id=ids["org_a"],
            )
            held_readiness = _command(
                held_readiness_connection,
                kind="readiness_evaluation",
                operation_id=uuid4(),
                payload={
                    "result_id": str(uuid4()),
                    "membership_id": str(ids["staff_membership_a"]),
                    "vehicle_id": str(vehicle_id),
                },
            )
            assert held_readiness["exact_retry"] is False
            revocation_started = Event()
            revocation_payload = {
                "result_id": str(uuid4()),
                "membership_id": str(ids["staff_membership_a"]),
                "capability_version_id": str(driver_result_id),
                "qualification_version_ids": [str(review_result_id)],
                "decision": "revoked",
                "reason_code": "concurrent_revocation",
                "authorization_valid_from": None,
                "authorization_valid_until": None,
            }
            with ThreadPoolExecutor(max_workers=1) as executor:
                revocation_future = executor.submit(
                    _run_concurrent_command,
                    basic,
                    revocation_started,
                    user_id=ids["manager_a"],
                    organization_id=ids["org_a"],
                    kind="driver_authorization",
                    operation_id=uuid4(),
                    payload=revocation_payload,
                )
                assert revocation_started.wait(timeout=2)
                with pytest.raises(FutureTimeoutError):
                    revocation_future.result(timeout=0.25)
                held_readiness_transaction.commit()
                revocation = revocation_future.result(timeout=5)
            assert revocation["result_id"] == UUID(str(revocation_payload["result_id"]))
        finally:
            if held_readiness_transaction.is_active:
                held_readiness_transaction.rollback()
            held_readiness_connection.close()

        retirement_connection = basic.connect()
        retirement_transaction = retirement_connection.begin()
        retirement_readiness_future = None
        retirement_readiness_operation = uuid4()
        try:
            _set_context(
                retirement_connection,
                user_id=ids["manager_a"],
                organization_id=ids["org_a"],
            )
            retirement = _command(
                retirement_connection,
                kind="vehicle_retire",
                operation_id=uuid4(),
                payload={
                    "result_id": str(vehicle_id),
                    "vehicle_id": str(vehicle_id),
                    "reason_code": "concurrent_retirement",
                },
            )
            assert retirement["result_id"] == vehicle_id
            retirement_readiness_started = Event()
            with ThreadPoolExecutor(max_workers=1) as executor:
                retirement_readiness_future = executor.submit(
                    _run_concurrent_command,
                    basic,
                    retirement_readiness_started,
                    user_id=ids["manager_a"],
                    organization_id=ids["org_a"],
                    kind="readiness_evaluation",
                    operation_id=retirement_readiness_operation,
                    payload={
                        "result_id": str(uuid4()),
                        "membership_id": str(ids["staff_membership_a"]),
                        "vehicle_id": str(vehicle_id),
                    },
                )
                assert retirement_readiness_started.wait(timeout=2)
                with pytest.raises(FutureTimeoutError):
                    retirement_readiness_future.result(timeout=0.25)
                retirement_transaction.commit()
                with pytest.raises(DBAPIError, match="transport_vehicle_not_found"):
                    retirement_readiness_future.result(timeout=5)
        finally:
            if retirement_transaction.is_active:
                retirement_transaction.rollback()
            retirement_connection.close()
        with database_admin.connect() as connection:
            assert (
                connection.scalar(
                    text(
                        "SELECT count(*) FROM transport_registry_command_receipts "
                        "WHERE client_operation_id=:operation_id"
                    ),
                    {"operation_id": retirement_readiness_operation},
                )
                == 0
            )

        _expect_command_error(
            basic,
            user_id=ids["staff_a"],
            organization_id=ids["org_a"],
            kind="driver_declaration",
            operation_id=uuid4(),
            payload=_driver_payload(ids["manager_membership_a"], uuid4()),
            marker="transport_command_scope_not_found",
        )
        _expect_command_error(
            basic,
            user_id=ids["manager_a"],
            organization_id=ids["org_b"],
            kind="driver_declaration",
            operation_id=uuid4(),
            payload=_driver_payload(ids["manager_membership_b"], uuid4()),
            marker="transport_command_forbidden",
        )

        atomic_operation = uuid4()
        atomic_result = uuid4()
        with database_admin.begin() as connection:
            connection.execute(
                text(
                    "CREATE FUNCTION public.caresync_test_0032_abort_receipt() "
                    "RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN "
                    f"IF NEW.client_operation_id='{atomic_operation}'::uuid THEN "
                    "RAISE EXCEPTION 'test_atomic_receipt_abort'; END IF; RETURN NEW; END $$"
                )
            )
            connection.execute(
                text(
                    "CREATE TRIGGER aaa_caresync_test_0032_abort_receipt BEFORE INSERT ON "
                    "transport_registry_command_receipts FOR EACH ROW EXECUTE FUNCTION "
                    "public.caresync_test_0032_abort_receipt()"
                )
            )
        _expect_command_error(
            basic,
            user_id=ids["staff_a"],
            organization_id=ids["org_a"],
            kind="driver_declaration",
            operation_id=atomic_operation,
            payload=_driver_payload(ids["staff_membership_a"], atomic_result),
            marker="test_atomic_receipt_abort",
        )
        with database_admin.begin() as connection:
            assert (
                connection.scalar(
                    text("SELECT count(*) FROM staff_driver_capability_versions WHERE id=:id"),
                    {"id": atomic_result},
                )
                == 0
            )
            assert (
                connection.scalar(
                    text(
                        "SELECT count(*) FROM transport_registry_command_receipts "
                        "WHERE client_operation_id=:operation"
                    ),
                    {"operation": atomic_operation},
                )
                == 0
            )
            assert (
                connection.scalar(
                    text("SELECT count(*) FROM audit_events WHERE entity_id=:id"),
                    {"id": atomic_result},
                )
                == 0
            )
            connection.execute(
                text(
                    "DROP TRIGGER aaa_caresync_test_0032_abort_receipt ON "
                    "transport_registry_command_receipts"
                )
            )
            connection.execute(text("DROP FUNCTION public.caresync_test_0032_abort_receipt()"))

        with database_admin.connect() as connection:
            receipt_count = connection.scalar(
                text(
                    "SELECT count(*) FROM transport_registry_command_receipts "
                    "WHERE organization_id=:organization_id"
                ),
                {"organization_id": ids["org_a"]},
            )
            public_transport_events = (
                connection.execute(
                    text(
                        "SELECT event_type,entity_type,entity_id,payload "
                        "FROM realtime_events WHERE organization_id=:organization_id "
                        "AND event_type='transport_registry.changed'"
                    ),
                    {"organization_id": ids["org_a"]},
                )
                .mappings()
                .all()
            )
            assert len(public_transport_events) == receipt_count
            assert {row["event_type"] for row in public_transport_events} == {
                "transport_registry.changed"
            }
            assert {row["entity_type"] for row in public_transport_events} == {"transport_registry"}
            assert {row["entity_id"] for row in public_transport_events} == {None}
            assert {
                json.dumps(row["payload"], sort_keys=True) for row in public_transport_events
            } == {
                json.dumps(
                    {"source": "audit_event", "refresh_required": True},
                    sort_keys=True,
                )
            }
            serialized_public_events = json.dumps(
                [dict(row) for row in public_transport_events],
                default=str,
                sort_keys=True,
            )
            assert str(readiness_operation) not in serialized_public_events
            assert str(readiness_id) not in serialized_public_events
            qualification_binding = connection.execute(
                text(
                    "SELECT qualification.evidence_reference_sha256,evidence.content_sha256,"
                    "evidence.scanner_engine,evidence.scanner_version,evidence.recorded_by_user_id "
                    "FROM staff_driver_qualification_versions AS qualification JOIN "
                    "staff_driver_qualification_evidence_objects AS evidence ON "
                    "evidence.organization_id=qualification.organization_id AND "
                    "evidence.membership_id=qualification.membership_id AND "
                    "evidence.qualification_version_id=qualification.id "
                    "WHERE qualification.id=:id"
                ),
                {"id": qualification_id},
            ).one()
            assert qualification_binding == (
                qualification_payload["content_sha256"],
                qualification_payload["content_sha256"],
                qualification_payload["scanner_engine"],
                qualification_payload["scanner_version"],
                ids["staff_a"],
            )
            for payload in submitted_vehicle_evidence:
                scan_binding = connection.execute(
                    text(
                        "SELECT evidence.content_sha256,scan.evidence_version_id,"
                        "scan.scanner_engine,scan.scanner_version,scan.scanner_signature,"
                        "scan.recorded_by_user_id FROM transport_vehicle_evidence_versions "
                        "AS evidence JOIN transport_vehicle_evidence_scan_facts AS scan ON "
                        "scan.organization_id=evidence.organization_id AND "
                        "scan.vehicle_id=evidence.vehicle_id AND "
                        "scan.evidence_version_id=evidence.id WHERE evidence.id=:id"
                    ),
                    {"id": UUID(str(payload["result_id"]))},
                ).one()
                assert scan_binding == (
                    payload["content_sha256"],
                    UUID(str(payload["result_id"])),
                    payload["scanner_engine"],
                    payload["scanner_version"],
                    None,
                    ids["staff_a"],
                )

            for table in AUTHORITY_FLAG_TABLES:
                asserted = connection.execute(
                    text(
                        f"SELECT count(*),count(*) FILTER (WHERE operational_driver_ready),"
                        f"count(*) FILTER (WHERE dispatch_authorized) FROM {table}"
                    )
                ).one()
                assert asserted[0] > 0
                assert asserted[1:] == (0, 0)

        with basic.begin() as connection:
            _set_context(connection, user_id=ids["staff_a"], organization_id=ids["org_a"])
            assert (
                connection.scalar(text("SELECT count(*) FROM transport_registry_command_receipts"))
                > 0
            )
            assert (
                connection.scalar(
                    text("SELECT count(*) FROM staff_driver_qualification_review_decisions")
                )
                == 0
            )
            assert connection.scalar(
                text("SELECT count(*) FROM transport_vehicle_evidence_scan_facts")
            ) == len(submitted_vehicle_evidence)
        with basic.begin() as connection:
            _set_context(
                connection,
                user_id=ids["manager_a"],
                organization_id=ids["org_a"],
            )
            assert (
                connection.scalar(text("SELECT count(*) FROM transport_registry_command_receipts"))
                > 0
            )
            assert (
                connection.scalar(
                    text("SELECT count(*) FROM staff_driver_qualification_review_decisions")
                )
                == 1
            )
            assert connection.scalar(
                text("SELECT count(*) FROM transport_vehicle_evidence_review_decisions")
            ) == len(verified_vehicle_evidence_ids)
        with basic.begin() as connection:
            _set_context(connection, user_id=ids["staff_a"], organization_id=ids["org_b"])
            assert (
                connection.scalar(text("SELECT count(*) FROM transport_registry_command_receipts"))
                == 0
            )
            assert (
                connection.scalar(text("SELECT count(*) FROM staff_driver_capability_versions"))
                == 0
            )

        with pytest.raises(DBAPIError), basic.begin() as connection:
            _set_context(connection, user_id=ids["staff_a"], organization_id=ids["org_a"])
            connection.execute(
                text("UPDATE staff_driver_capability_versions SET status=status WHERE id=:id"),
                {"id": driver_result_id},
            )
        with pytest.raises(DBAPIError), evidence_ingest.begin() as connection:
            _set_context(connection, user_id=ids["staff_a"], organization_id=ids["org_a"])
            connection.execute(
                text("DELETE FROM transport_vehicle_evidence_scan_facts WHERE id=:id"),
                {"id": UUID(str(submitted_vehicle_evidence[0]["scan_fact_id"]))},
            )

        _assert_policy_identity_tampering_fails_closed(
            database_admin,
            basic_password=basic_password,
            evidence_password=evidence_password,
        )

        downgrade = _alembic("downgrade", "0031_driver_vehicle_registry")
        assert downgrade.returncode != 0
        assert "downgrade refused" in (downgrade.stdout + downgrade.stderr).lower()
        with database_admin.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
                "0032_transport_commands"
            )
    finally:
        if evidence_ingest is not None:
            evidence_ingest.dispose()
        if basic is not None:
            basic.dispose()
        if database_admin is not None:
            database_admin.dispose()
        if database_created:
            with cluster.connect() as connection:
                connection.execute(
                    text(
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        "WHERE datname=:name AND pid<>pg_backend_pid()"
                    ),
                    {"name": DATABASE_NAME},
                )
                connection.execute(text(f'DROP DATABASE IF EXISTS "{DATABASE_NAME}"'))
        if role_namespace_owned:
            with cluster.connect() as connection:
                for role in (EVIDENCE_ROLE, BASIC_ROLE, COMMAND_OWNER_ROLE):
                    connection.execute(text(f'DROP ROLE IF EXISTS "{role}"'))
        cluster.dispose()
