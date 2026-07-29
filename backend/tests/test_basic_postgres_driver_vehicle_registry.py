"""Opt-in PostgreSQL 17 certification for the source-only 0031 registry.

The test creates and drops only a named database on an explicitly supplied
disposable loopback cluster. Protected CareSync ports and non-loopback targets
are rejected before any connection is attempted.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import DBAPIError

from app.core.config import Settings
from app.db.session import Database
from app.main import create_app

DISPOSABLE_URL_TEXT = os.getenv("BASIC_POSTGRES_DRIVER_REGISTRY_TEST_URL")
BACKEND_ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = BACKEND_ROOT / "scripts" / "bootstrap_basic_runtime_role.sql"
PSQL = Path(os.getenv("CARESYNC_PSQL", "/opt/homebrew/opt/postgresql@17/bin/psql"))
DATABASE_NAME = "caresync"
RUNTIME_ROLE = "caresync_basic_app"
CURRENT_REVISION = "0031_driver_vehicle_registry"
PROTECTED_PORTS = {5432, 5433, 5434}
REGISTRY_TABLES = (
    "staff_driver_capability_versions",
    "staff_driver_qualification_versions",
    "staff_driver_authorization_decisions",
    "staff_driver_readiness_decisions",
    "transport_vehicles",
    "transport_vehicle_versions",
    "transport_vehicle_evidence_versions",
)
REGISTRY_FUNCTIONS = (
    "caresync_0031_immutable_fact()",
    "caresync_0031_capability_guard()",
    "caresync_0031_qualification_guard()",
    "caresync_0031_authorization_guard()",
    "caresync_0031_vehicle_guard()",
    "caresync_0031_vehicle_version_guard()",
    "caresync_0031_vehicle_evidence_guard()",
    "caresync_0031_readiness_guard()",
)


def _guard_disposable_url(value: str) -> URL:
    url = make_url(value)
    if not url.drivername.startswith("postgresql"):
        raise RuntimeError("0031 PostgreSQL certification requires a PostgreSQL URL")
    if url.host not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError("0031 PostgreSQL certification requires a loopback host")
    if url.port is None or url.port in PROTECTED_PORTS or not 1 <= url.port <= 65535:
        raise RuntimeError("0031 PostgreSQL certification refuses protected/invalid ports")
    if url.database != "postgres":
        raise RuntimeError("Disposable URL must target the cluster's postgres database")
    if not url.username:
        raise RuntimeError("Disposable URL must include an administrative user")
    return url


ADMIN_CLUSTER_URL = _guard_disposable_url(DISPOSABLE_URL_TEXT) if DISPOSABLE_URL_TEXT else None

pytestmark = pytest.mark.skipif(
    ADMIN_CLUSTER_URL is None,
    reason=(
        "BASIC_POSTGRES_DRIVER_REGISTRY_TEST_URL must name a disposable "
        "loopback PostgreSQL 17 cluster"
    ),
)


def _database_url(user: str, password: str | None = None) -> URL:
    assert ADMIN_CLUSTER_URL is not None
    return URL.create(
        "postgresql+psycopg",
        username=user,
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


def _settings(runtime_password: str) -> Settings:
    assert ADMIN_CLUSTER_URL is not None
    return Settings(
        _env_file=None,
        environment="test",
        database_type="postgres",
        database_host=str(ADMIN_CLUSTER_URL.host),
        database_port=int(ADMIN_CLUSTER_URL.port or 0),
        database_user=RUNTIME_ROLE,
        database_password=runtime_password,
        database_name=DATABASE_NAME,
        database_ssl=False,
        database_read_only=False,
        enable_advanced_routes=False,
        jwt_secret="postgres-0031-test-secret-with-at-least-thirty-two-bytes",
    )


def _set_context(connection, *, user_id: UUID, organization_id: UUID) -> None:
    connection.execute(
        text("SELECT set_config('app.current_user_id',:value,true)"),
        {"value": str(user_id)},
    )
    connection.execute(
        text("SELECT set_config('app.current_organization_id',:value,true)"),
        {"value": str(organization_id)},
    )


def _register(client: TestClient, suffix: str, label: str) -> tuple[dict, dict[str, str]]:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"registry-{label}-{suffix}@example.test",
            "password": "secure-password-123",
            "first_name": label.title(),
            "last_name": "Owner",
            "organization_name": f"Registry {label.title()} {suffix}",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return body, {"Authorization": f"Bearer {body['access_token']}"}


def _identity(connection, email: str) -> tuple[UUID, UUID, UUID, UUID]:
    row = connection.execute(
        text(
            "SELECT membership.organization_id,membership.id,membership.role_id,user_account.id "
            "FROM users AS user_account JOIN organization_memberships AS membership "
            "ON membership.user_id=user_account.id WHERE user_account.email=:email"
        ),
        {"email": email},
    ).one()
    return row[0], row[1], row[2], row[3]


def _seed_registry(
    connection,
    *,
    organization_id: UUID,
    membership_id: UUID,
    target_user_id: UUID,
    reviewer_user_id: UUID,
    include_authorization: bool,
    include_vehicle: bool,
) -> dict[str, UUID]:
    identifiers = {
        "capability": uuid4(),
        "qualification": uuid4(),
        "authorization": uuid4(),
        "vehicle": uuid4(),
        "vehicle_version": uuid4(),
        "evidence": uuid4(),
        "readiness": uuid4(),
    }
    connection.execute(
        text(
            "INSERT INTO staff_driver_capability_versions "
            "(id,organization_id,membership_id,version_number,status,willing_to_drive,"
            "licence_jurisdiction,licence_class,vehicle_access,preferred_service_radius_km,"
            "source_kind,effective_at,recorded_by_user_id) VALUES "
            "(:id,:org,:membership,1,'declared',true,'CA-AB','5','personal_vehicle',25,"
            "'staff_self',now(),:actor)"
        ),
        {
            "id": identifiers["capability"],
            "org": organization_id,
            "membership": membership_id,
            "actor": target_user_id,
        },
    )
    connection.execute(
        text(
            "INSERT INTO staff_driver_qualification_versions "
            "(id,organization_id,membership_id,qualification_type,version_number,status,"
            "jurisdiction,qualification_class,identifier_last4,issue_date,expiry_date,"
            "evidence_reference_sha256,effective_at,recorded_by_user_id) VALUES "
            "(:id,:org,:membership,'driver_licence',1,'verified','CA-AB','5','1234',"
            "current_date-365,current_date+365,:digest,now(),:actor)"
        ),
        {
            "id": identifiers["qualification"],
            "org": organization_id,
            "membership": membership_id,
            "digest": "a" * 64,
            "actor": target_user_id,
        },
    )

    if not include_authorization:
        return identifiers

    authorization_values = {
        "id": identifiers["authorization"],
        "org": organization_id,
        "membership": membership_id,
        "capability": identifiers["capability"],
        "qualifications": f'["{identifiers["qualification"]}"]',
        "reviewer": reviewer_user_id,
    }
    connection.execute(
        text(
            "INSERT INTO staff_driver_authorization_decisions "
            "(id,organization_id,membership_id,decision_sequence,capability_version_id,"
            "qualification_version_ids,decision,reason_code,authorization_valid_from,"
            "authorization_valid_until,reviewed_by_user_id,reviewed_at,"
            "operational_driver_ready,dispatch_authorized) VALUES "
            "(:id,:org,:membership,1,:capability,CAST(:qualifications AS jsonb),"
            "'authorized','independent_review_complete',now(),now()+interval '180 days',"
            ":reviewer,now(),false,false)"
        ),
        authorization_values,
    )
    if not include_vehicle:
        return identifiers

    connection.execute(
        text(
            "INSERT INTO transport_vehicles "
            "(id,organization_id,owner_kind,staff_owner_membership_id,created_by_user_id) "
            "VALUES (:id,:org,'staff_personal',:membership,:actor)"
        ),
        {
            "id": identifiers["vehicle"],
            "org": organization_id,
            "membership": membership_id,
            "actor": target_user_id,
        },
    )
    connection.execute(
        text(
            "INSERT INTO transport_vehicle_versions "
            "(id,organization_id,vehicle_id,version_number,make,model,model_year,color,"
            "plate_token,plate_jurisdiction,passenger_capacity,child_passenger_capacity,"
            "wheelchair_accessible,effective_at,recorded_by_user_id) VALUES "
            "(:id,:org,:vehicle,1,'Toyota','Sienna',2022,'Blue','PGTEST','CA-AB',7,6,"
            "false,now(),:actor)"
        ),
        {
            "id": identifiers["vehicle_version"],
            "org": organization_id,
            "vehicle": identifiers["vehicle"],
            "actor": target_user_id,
        },
    )
    connection.execute(
        text(
            "INSERT INTO transport_vehicle_evidence_versions "
            "(id,organization_id,vehicle_id,vehicle_version_id,evidence_type,version_number,"
            "status,issue_date,expiry_date,original_filename,media_type,byte_size,"
            "content_sha256,ciphertext_sha256,storage_reference,encryption_key_id,"
            "recorded_by_user_id) VALUES "
            "(:id,:org,:vehicle,:vehicle_version,'insurance',1,'verified',current_date-30,"
            "current_date+335,'insurance.pdf','application/pdf',1024,:content,:ciphertext,"
            "'transport/postgres/insurance.enc','pg-test-key',:actor)"
        ),
        {
            "id": identifiers["evidence"],
            "org": organization_id,
            "vehicle": identifiers["vehicle"],
            "vehicle_version": identifiers["vehicle_version"],
            "content": "b" * 64,
            "ciphertext": "c" * 64,
            "actor": target_user_id,
        },
    )
    connection.execute(
        text(
            "INSERT INTO staff_driver_readiness_decisions "
            "(id,organization_id,membership_id,decision_sequence,capability_version_id,"
            "authorization_decision_id,vehicle_id,vehicle_version_id,"
            "vehicle_evidence_version_ids,decision,reason_codes,evaluated_by_user_id,"
            "evaluated_at,operational_driver_ready,dispatch_authorized) VALUES "
            "(:id,:org,:membership,1,:capability,:authorization,:vehicle,:vehicle_version,"
            "CAST(:evidence AS jsonb),'incomplete',"
            "CAST('[\"dispatch_policy_not_activated\"]' AS jsonb),:reviewer,now(),false,false)"
        ),
        {
            "id": identifiers["readiness"],
            "org": organization_id,
            "membership": membership_id,
            "capability": identifiers["capability"],
            "authorization": identifiers["authorization"],
            "vehicle": identifiers["vehicle"],
            "vehicle_version": identifiers["vehicle_version"],
            "evidence": f'["{identifiers["evidence"]}"]',
            "reviewer": reviewer_user_id,
        },
    )
    return identifiers


def test_postgres_17_registry_migration_rls_and_fail_closed_runtime() -> None:
    assert ADMIN_CLUSTER_URL is not None
    assert PSQL.is_file(), f"PostgreSQL 17 psql is unavailable at {PSQL}"
    cluster = create_engine(ADMIN_CLUSTER_URL, isolation_level="AUTOCOMMIT")
    database_admin = None
    runtime = None
    database_created = False
    runtime_namespace_owned = False
    runtime_password = f"registry-{uuid4().hex}"
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
            ), "The 0031 test database must not already exist"
            assert (
                connection.scalar(
                    text("SELECT 1 FROM pg_roles WHERE rolname=:name"),
                    {"name": RUNTIME_ROLE},
                )
                is None
            ), "The 0031 test requires a fresh disposable cluster role namespace"
            runtime_namespace_owned = True
            connection.execute(text(f'CREATE DATABASE "{DATABASE_NAME}"'))
            database_created = True

        admin_database_url = ADMIN_CLUSTER_URL.set(database=DATABASE_NAME)
        database_admin = create_engine(admin_database_url)
        with database_admin.begin() as connection:
            connection.execute(text("REVOKE CREATE ON SCHEMA public FROM PUBLIC"))

        # This is a frozen 0031 certification. Repository head can advance
        # without changing the schema boundary this proof is responsible for.
        migration = _alembic("upgrade", CURRENT_REVISION)
        assert migration.returncode == 0, migration.stdout + migration.stderr
        with database_admin.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
                CURRENT_REVISION
            )

        bootstrapped = _bootstrap()
        assert bootstrapped.returncode == 0, bootstrapped.stdout + bootstrapped.stderr
        with cluster.begin() as connection:
            connection.execute(text(f"ALTER ROLE {RUNTIME_ROLE} PASSWORD '{runtime_password}'"))

        settings = _settings(runtime_password)
        database = Database(settings)
        database.assert_basic_runtime_identity()
        assert database.has_driver_vehicle_registry() is True
        database.dispose()

        with database_admin.connect() as connection:
            hardened = connection.execute(
                text(
                    "SELECT count(*) FROM pg_class WHERE oid=ANY(CAST(:tables AS regclass[])) "
                    "AND relrowsecurity AND relforcerowsecurity"
                ),
                {"tables": list(REGISTRY_TABLES)},
            ).scalar_one()
            assert hardened == len(REGISTRY_TABLES)
            role = connection.execute(
                text(
                    "SELECT rolsuper,rolbypassrls,rolinherit,rolcreaterole,rolcreatedb,"
                    "rolreplication FROM pg_roles WHERE rolname=:name"
                ),
                {"name": RUNTIME_ROLE},
            ).one()
            assert role == (False, False, False, False, False, False)
            privileges = connection.execute(
                text(
                    "SELECT expected.name,"
                    "has_table_privilege(:runtime,to_regclass('public.' || expected.name),"
                    "'SELECT'),"
                    "has_table_privilege(:runtime,to_regclass('public.' || expected.name),"
                    "'INSERT'),"
                    "has_table_privilege(:runtime,to_regclass('public.' || expected.name),"
                    "'UPDATE'),"
                    "has_table_privilege(:runtime,to_regclass('public.' || expected.name),"
                    "'DELETE') "
                    "FROM unnest(CAST(:tables AS text[])) AS expected(name)"
                ),
                {"runtime": RUNTIME_ROLE, "tables": list(REGISTRY_TABLES)},
            ).all()
            assert all(
                can_read and not insert and not update and not delete
                for _, can_read, insert, update, delete in privileges
            )
            function_acl = connection.execute(
                text(
                    "SELECT expected.signature,"
                    "COALESCE(has_function_privilege(:runtime,procedure.oid,'EXECUTE'),false),"
                    "EXISTS (SELECT 1 FROM aclexplode(COALESCE("
                    "procedure.proacl,acldefault('f',procedure.proowner))) AS acl "
                    "WHERE acl.grantee=0 AND acl.privilege_type='EXECUTE') "
                    "FROM unnest(CAST(:functions AS text[])) AS expected(signature) "
                    "LEFT JOIN pg_proc AS procedure ON procedure.oid="
                    "to_regprocedure('public.' || expected.signature)"
                ),
                {"runtime": RUNTIME_ROLE, "functions": list(REGISTRY_FUNCTIONS)},
            ).all()
            assert all(
                not app_execute and not public_execute
                for _, app_execute, public_execute in function_acl
            )

        application = create_app(settings)
        suffix = uuid4().hex
        with TestClient(application) as client:
            tenant_a, headers_a = _register(client, suffix, "alpha")
            tenant_b, headers_b = _register(client, suffix, "beta")
            email_a = f"registry-alpha-{suffix}@example.test"
            email_b = f"registry-beta-{suffix}@example.test"
            with database_admin.begin() as connection:
                org_a, membership_a, role_a, user_a = _identity(connection, email_a)
                org_b, membership_b, _, user_b = _identity(connection, email_b)
                reviewer = uuid4()
                reviewer_membership = uuid4()
                connection.execute(
                    text(
                        "INSERT INTO users "
                        "(id,email,password_hash,first_name,last_name,is_active,auth_version) "
                        "VALUES (:id,:email,'unused','Independent','Reviewer',true,1)"
                    ),
                    {"id": reviewer, "email": f"reviewer-{suffix}@example.test"},
                )
                connection.execute(
                    text(
                        "INSERT INTO organization_memberships "
                        "(id,organization_id,user_id,role_id,status,joined_at) "
                        "VALUES (:id,:org,:user,:role,'active',now())"
                    ),
                    {
                        "id": reviewer_membership,
                        "org": org_a,
                        "user": reviewer,
                        "role": role_a,
                    },
                )
                ids_a = _seed_registry(
                    connection,
                    organization_id=org_a,
                    membership_id=membership_a,
                    target_user_id=user_a,
                    reviewer_user_id=reviewer,
                    include_authorization=True,
                    include_vehicle=True,
                )
                ids_b = _seed_registry(
                    connection,
                    organization_id=org_b,
                    membership_id=membership_b,
                    target_user_id=user_b,
                    reviewer_user_id=user_b,
                    include_authorization=False,
                    include_vehicle=False,
                )

            # Tenant B has its own facts but no authorization or vehicle. This
            # makes a cross-tenant leak observable without introducing a
            # deliberately invalid self-review into the shared seed transaction.
            assert ids_a["capability"]
            assert ids_b["capability"]

            self_marker = client.get("/api/v1/staff/self", headers=headers_a)
            assert self_marker.status_code == 200, self_marker.text
            marker = self_marker.json()["driver_vehicle_registry"]
            assert marker["schema_version"] == "0031"
            assert marker["runtime_available"] is True
            assert marker["operational_driver_ready"] is False
            assert marker["dispatch_authorized"] is False
            projection = client.get("/api/v1/staff/self/transport-registry", headers=headers_a)
            assert projection.status_code == 200, projection.text
            assert projection.headers["cache-control"] == "private, no-store"
            body = projection.json()
            assert body["latest_readiness_decision"]["decision"] == "incomplete"
            assert body["operational_driver_ready"] is False
            assert body["dispatch_authorized"] is False
            assert body["vehicles"][0]["current_version"]["make"] == "Toyota"
            assert "storage_reference" not in projection.text
            assert "content_sha256" not in projection.text
            assert "child_id" not in projection.text
            assert "address" not in projection.text

            # Authenticated tenant B cannot see tenant A's registry projection.
            other_projection = client.get(
                "/api/v1/staff/self/transport-registry", headers=headers_b
            )
            assert other_projection.status_code == 200, other_projection.text
            assert other_projection.json()["vehicles"] == []
            assert tenant_a["user"]["organization_id"] != tenant_b["user"]["organization_id"]

        runtime = create_engine(_database_url(RUNTIME_ROLE, runtime_password))
        with runtime.begin() as connection:
            _set_context(connection, user_id=user_a, organization_id=org_a)
            assert (
                connection.scalar(text("SELECT count(*) FROM staff_driver_capability_versions"))
                == 1
            )
        with runtime.begin() as connection:
            _set_context(connection, user_id=user_a, organization_id=org_b)
            assert (
                connection.scalar(text("SELECT count(*) FROM staff_driver_capability_versions"))
                == 0
            )

        for statement, identifier in (
            (
                "UPDATE staff_driver_capability_versions SET status=status WHERE id=:id",
                ids_a["capability"],
            ),
            (
                "DELETE FROM transport_vehicle_evidence_versions WHERE id=:id",
                ids_a["evidence"],
            ),
        ):
            with pytest.raises(DBAPIError), database_admin.begin() as connection:
                connection.execute(text(statement), {"id": identifier})

        with pytest.raises(DBAPIError), database_admin.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO staff_driver_authorization_decisions "
                    "(id,organization_id,membership_id,decision_sequence,capability_version_id,"
                    "qualification_version_ids,decision,reason_code,authorization_valid_from,"
                    "authorization_valid_until,reviewed_by_user_id,reviewed_at,"
                    "operational_driver_ready,dispatch_authorized) VALUES "
                    "(:id,:org,:membership,2,:capability,CAST(:qualifications AS jsonb),"
                    "'authorized','self_review',now(),now()+interval '30 days',:target,now(),"
                    "false,false)"
                ),
                {
                    "id": uuid4(),
                    "org": org_a,
                    "membership": membership_a,
                    "capability": ids_a["capability"],
                    "qualifications": f'["{ids_a["qualification"]}"]',
                    "target": user_a,
                },
            )
        with pytest.raises(DBAPIError), database_admin.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO staff_driver_authorization_decisions "
                    "(id,organization_id,membership_id,decision_sequence,capability_version_id,"
                    "qualification_version_ids,decision,reason_code,authorization_valid_from,"
                    "authorization_valid_until,reviewed_by_user_id,reviewed_at,"
                    "operational_driver_ready,dispatch_authorized) VALUES "
                    "(:id,:org,:membership,2,:capability,CAST(:qualifications AS jsonb),"
                    "'authorized','overlong_window',now(),now()+interval '730 days',:reviewer,"
                    "now(),false,false)"
                ),
                {
                    "id": uuid4(),
                    "org": org_a,
                    "membership": membership_a,
                    "capability": ids_a["capability"],
                    "qualifications": f'["{ids_a["qualification"]}"]',
                    "reviewer": reviewer,
                },
            )
        with pytest.raises(DBAPIError), database_admin.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO staff_driver_readiness_decisions "
                    "(id,organization_id,membership_id,decision_sequence,capability_version_id,"
                    "authorization_decision_id,vehicle_evidence_version_ids,decision,reason_codes,"
                    "evaluated_by_user_id,evaluated_at,operational_driver_ready,"
                    "dispatch_authorized) VALUES "
                    "(:id,:org,:membership,2,:capability,:authorization,'[]'::jsonb,'blocked',"
                    "'[\"forged_ready\"]'::jsonb,:reviewer,now(),true,true)"
                ),
                {
                    "id": uuid4(),
                    "org": org_a,
                    "membership": membership_a,
                    "capability": ids_a["capability"],
                    "authorization": ids_a["authorization"],
                    "reviewer": reviewer,
                },
            )

        downgrade = _alembic("downgrade", "0030_staff_screening_paths")
        assert downgrade.returncode != 0
        assert "downgrade refused" in (downgrade.stdout + downgrade.stderr).lower()
        with database_admin.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
                CURRENT_REVISION
            )
    finally:
        if runtime is not None:
            runtime.dispose()
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
        if runtime_namespace_owned:
            with cluster.connect() as connection:
                connection.execute(text(f"DROP ROLE IF EXISTS {RUNTIME_ROLE}"))
        cluster.dispose()
