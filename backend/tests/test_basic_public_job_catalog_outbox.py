"""Durability, privacy, and replay proofs for the 0038 public job outbox."""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import func, inspect, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from alembic import command
from app.api.basic.hiring import router as legacy_hiring_router
from app.api.basic.marketplace_realtime import (
    _candidate_events,
    _candidate_latest_cursor,
    _frame,
)
from app.basic.models import (
    AtsApplication,
    AtsCandidate,
    AtsJob,
    BasicBase,
    MarketplaceApplicationLink,
    MarketplaceInterest,
    MarketplaceJob,
    Organization,
    OrganizationMembership,
    PublicJobCatalogEvent,
    RealtimeEvent,
    User,
)
from app.basic.security import set_rls_organization, set_rls_user
from app.core.config import Settings
from app.db.session import Database
from app.main import create_app

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PREVIOUS_REVISION = "0037_billing_agreement_scope"
CURRENT_REVISION = "0038_public_job_catalog_outbox"
PASSWORD = "secure-password-123"
POSTGRES_OUTBOX_TEST_URL = os.getenv("BASIC_POSTGRES_PUBLIC_JOB_OUTBOX_TEST_URL")
BOOTSTRAP = BACKEND_ROOT / "scripts" / "bootstrap_basic_runtime_role.sql"
POSTGRES_RUNTIME_ROLES = (
    "caresync_basic_app",
    "caresync_transport_command_owner",
    "caresync_transport_evidence_ingest",
)


def _config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Config, Path]:
    database_path = tmp_path / "caresync.db"
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DATABASE_TYPE", "sqlite")
    monkeypatch.setenv("DATABASE_PATH", str(database_path))
    monkeypatch.setenv("DATABASE_NAME", "caresync")
    monkeypatch.setenv("DATABASE_READ_ONLY", "false")
    monkeypatch.setenv("ENABLE_ADVANCED_ROUTES", "false")
    return Config(str(BACKEND_ROOT / "alembic.ini")), database_path


def _settings(database_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        database_type="sqlite",
        database_path=database_path,
        database_name="caresync",
        database_read_only=False,
        enable_advanced_routes=False,
        jwt_secret="public-job-outbox-test-secret-at-least-thirty-two-bytes",
    )


def _postgres_settings(url: sa.engine.URL) -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        database_type="postgres",
        database_host=str(url.host),
        database_port=int(url.port or 0),
        database_user=str(url.username),
        database_password=str(url.password or ""),
        database_name=str(url.database),
        database_ssl=False,
        database_read_only=False,
        enable_advanced_routes=False,
        jwt_secret="public-job-outbox-postgres-test-secret-at-least-32-bytes",
    )


def _run_bootstrap(admin_url: sa.engine.URL, database_name: str) -> None:
    configured = os.getenv("CARESYNC_PSQL")
    psql = Path(
        configured
        or shutil.which("psql")
        or "/opt/homebrew/Cellar/postgresql@17/17.8/bin/psql"
    )
    assert psql.exists(), f"PostgreSQL client not found at {psql}"
    environment = os.environ.copy()
    if admin_url.password:
        environment["PGPASSWORD"] = str(admin_url.password)
    completed = subprocess.run(
        [
            str(psql),
            "-v",
            "ON_ERROR_STOP=1",
            "-h",
            str(admin_url.host),
            "-p",
            str(admin_url.port),
            "-U",
            str(admin_url.username),
            "-d",
            database_name,
            "-f",
            str(BOOTSTRAP),
        ],
        cwd=BACKEND_ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def _owner(client: TestClient, marker: str) -> tuple[dict, dict[str, str]]:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"outbox-owner-{marker}@example.test",
            "password": PASSWORD,
            "first_name": "Outbox",
            "last_name": "Owner",
            "organization_name": f"Outbox Centre {marker}",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return body, {"Authorization": f"Bearer {body['access_token']}"}


def _candidate(
    client: TestClient,
    marker: str,
) -> tuple[dict, dict[str, str]]:
    response = client.post(
        "/api/v1/marketplace/auth/register",
        json={
            "email": f"outbox-candidate-{marker}@example.test",
            "password": PASSWORD,
            "first_name": "Catalog",
            "last_name": "Candidate",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    headers = {"Authorization": f"Bearer {body['access_token']}"}
    personal = client.patch(
        "/api/v1/marketplace/personal-profile",
        headers=headers,
        json={"date_of_birth": "1995-05-20", "phone": "+1 780 555 0199"},
    )
    assert personal.status_code == 200, personal.text
    profile = client.put(
        "/api/v1/marketplace/profile",
        headers=headers,
        json={
            "city": "Edmonton",
            "headline": "Student educator",
            "bio": None,
            "certification_type": None,
            "certification_number": None,
            "certification_expiry_date": None,
            "work_history": [],
            "discoverable": False,
        },
    )
    assert profile.status_code == 200, profile.text
    return body, headers


def _create_job(client: TestClient, headers: dict[str, str], marker: str) -> dict:
    response = client.post(
        "/api/v1/ats/jobs",
        headers=headers,
        json={
            "title": f"Private title {marker}",
            "description": f"Private employer description {marker}",
            "employment_type": "full_time",
            "location": "Edmonton",
            "requirements": [f"Private requirement {marker}"],
            "openings": 1,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _status(
    client: TestClient,
    headers: dict[str, str],
    job: dict,
    target: str,
) -> dict:
    response = client.post(
        f"/api/v1/ats/jobs/{job['id']}/status",
        headers=headers,
        json={
            "status": target,
            "expected_version": job["version"],
            "reason": f"Move listing to {target}",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_migration_uses_frozen_local_schema_not_live_orm() -> None:
    migration_path = (
        BACKEND_ROOT / "alembic" / "versions" / "0038_public_job_catalog_outbox.py"
    )
    source = migration_path.read_text(encoding="utf-8")
    assert "from app.basic.models import" not in source
    spec = importlib.util.spec_from_file_location("public_job_catalog_0038", migration_path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert migration.PUBLIC_JOB_CATALOG_TABLE.metadata is not BasicBase.metadata
    assert tuple(migration.PUBLIC_JOB_CATALOG_TABLE.columns.keys()) == (
        "sequence_id",
        "event_id",
        "listing_id",
        "event_type",
        "public_status",
        "listing_version",
        "occurred_at",
    )


def test_postgres_backfill_rejects_force_rls_drift_and_restores_on_python_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration_path = (
        BACKEND_ROOT / "alembic" / "versions" / "0038_public_job_catalog_outbox.py"
    )
    spec = importlib.util.spec_from_file_location(
        "public_job_catalog_force_0038",
        migration_path,
    )
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    class ForceBind:
        def __init__(self, states: dict[str, bool]) -> None:
            self.states = states

        def execute(self, _statement):
            return [
                SimpleNamespace(relname=name, relforcerowsecurity=forced)
                for name, forced in self.states.items()
            ]

    executed: list[str] = []
    monkeypatch.setattr(migration.op, "execute", executed.append)
    with pytest.raises(RuntimeError, match="must both FORCE RLS"):
        migration._postgres_backfill_with_force_restored(
            ForceBind({"ats_jobs": False, "realtime_events": True})
        )
    assert executed == []

    def fail_backfill(_bind) -> None:
        raise ValueError("synthetic Python failure")

    monkeypatch.setattr(migration, "_backfill_final_catalog_state", fail_backfill)
    with pytest.raises(ValueError, match="synthetic Python failure"):
        migration._postgres_backfill_with_force_restored(
            ForceBind({"ats_jobs": True, "realtime_events": True})
        )
    assert executed == [
        "ALTER TABLE public.ats_jobs NO FORCE ROW LEVEL SECURITY",
        "ALTER TABLE public.realtime_events NO FORCE ROW LEVEL SECURITY",
        "ALTER TABLE public.ats_jobs FORCE ROW LEVEL SECURITY",
        "ALTER TABLE public.realtime_events FORCE ROW LEVEL SECURITY",
    ]


def test_runtime_bootstrap_rebuilds_and_audits_exact_0038_read_boundary() -> None:
    bootstrap = BOOTSTRAP.read_text(encoding="utf-8")
    assert (
        "REVOKE ALL ON TABLE public.alembic_version\n"
        "    FROM PUBLIC, caresync_basic_app;"
    ) in bootstrap
    assert (
        "REVOKE ALL ON TABLE public.public_job_catalog_events\n"
        "        FROM PUBLIC, caresync_basic_app;"
    ) in bootstrap
    assert (
        "GRANT SELECT ON TABLE public.public_job_catalog_events\n"
        "        TO caresync_basic_app;"
    ) in bootstrap
    audit = bootstrap.split("DO $public_job_catalog_audit$", 1)[1].split(
        "$public_job_catalog_audit$;",
        1,
    )[0]
    assert "pg_catalog.aclexplode" in audit
    assert "privilege.grantee=0" in audit
    assert "privilege.privilege_type<>'SELECT'" in audit
    assert "pg_catalog.has_function_privilege" in audit
    assert "public_job_catalog_events_public_read" in audit
    assert "realtime_events_public_job_catalog" in audit
    assert "writer_owner" in audit


def test_metadata_only_schema_stays_on_legacy_replay_without_poll_inspection(
    tmp_path: Path,
) -> None:
    database_directory = tmp_path / "metadata-only"
    database_directory.mkdir()
    settings = _settings(database_directory / "caresync.db")
    database = Database(settings)
    try:
        BasicBase.metadata.create_all(database.engine)
        assert database.has_public_job_catalog_outbox() is False
        # The result is process/Engine scoped and remains cached; realtime
        # polling never repeats catalog inspection.
        with database.engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TRIGGER metadata_only_probe AFTER INSERT ON realtime_events "
                "BEGIN SELECT 1; END"
            )
        assert database.has_public_job_catalog_outbox() is False
    finally:
        database.dispose()


def test_0037_runtime_uses_legacy_candidate_replay_without_querying_outbox(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, database_path = _config(tmp_path, monkeypatch)
    command.upgrade(config, PREVIOUS_REVISION)
    application = create_app(_settings(database_path))
    with TestClient(application) as client:
        assert application.state.public_job_catalog_outbox_enabled is False
        _, owner_headers = _owner(client, uuid4().hex)
        observer, _ = _candidate(client, f"legacy-observer-{uuid4().hex}")
        job = _status(
            client,
            owner_headers,
            _create_job(client, owner_headers, "legacy-open"),
            "open",
        )
        with application.state.database.session_factory() as session:
            observer_id = UUID(observer["user_id"])
            replay = _candidate_events(session, observer_id, 0, 100)
            assert any(
                event.event_type == "job.status_changed"
                and event.entity_id == UUID(job["id"])
                for event in replay
            )
            assert _candidate_latest_cursor(session, observer_id) >= max(
                event.sequence_id for event in replay
            )


def test_0038_revision_with_all_outbox_objects_missing_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, database_path = _config(tmp_path, monkeypatch)
    command.upgrade(config, CURRENT_REVISION)
    engine = sa.create_engine(f"sqlite:///{database_path}")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "DROP TRIGGER realtime_events_public_job_catalog"
        )
        connection.exec_driver_sql("DROP TABLE public_job_catalog_events")
    engine.dispose()
    database = Database(_settings(database_path))
    try:
        with pytest.raises(RuntimeError, match="0038 public-job catalog outbox"):
            database.has_public_job_catalog_outbox()
    finally:
        database.dispose()


def test_legacy_hiring_status_route_flushes_before_public_outbox_event(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, database_path = _config(tmp_path, monkeypatch)
    command.upgrade(config, CURRENT_REVISION)
    application = create_app(_settings(database_path))
    application.include_router(legacy_hiring_router, prefix="/api/v1")
    with TestClient(application) as client:
        # The route is retired from production mounting; exercise its isolated
        # compatibility contract to keep future migrations safe.
        application.state.staff_screening_pathways_enabled = False
        _, owner_headers = _owner(client, f"legacy-route-{uuid4().hex}")
        created = client.post(
            "/api/v1/hiring/listings",
            headers=owner_headers,
            json={
                "title": "Compatibility educator",
                "location": "Edmonton",
                "employment_type": "full_time",
                "summary": "Compatibility route projection proof",
                "openings": 1,
            },
        )
        assert created.status_code == 201, created.text
        listing = created.json()
        for status in ("open", "paused", "closed"):
            changed = client.patch(
                f"/api/v1/hiring/listings/{listing['id']}",
                headers=owner_headers,
                json={"status": status},
            )
            assert changed.status_code == 200, changed.text
            listing = changed.json()

        with application.state.database.session_factory() as session:
            rows = list(
                session.scalars(
                    select(PublicJobCatalogEvent)
                    .where(
                        PublicJobCatalogEvent.listing_id
                        == UUID(listing["id"])
                    )
                    .order_by(PublicJobCatalogEvent.sequence_id)
                )
            )
            assert [
                (row.event_type, row.public_status, row.listing_version)
                for row in rows
            ] == [
                ("job.status_changed", "open", 2),
                ("job.status_changed", "paused", 3),
                ("job.status_changed", "closed", 4),
            ]


def test_upgrade_backfills_only_final_public_state_and_preserves_applied_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, database_path = _config(tmp_path, monkeypatch)
    command.upgrade(config, PREVIOUS_REVISION)
    application = create_app(_settings(database_path))
    with TestClient(application) as client:
        owner, owner_headers = _owner(client, uuid4().hex)
        applicant, applicant_headers = _candidate(client, f"applied-{uuid4().hex}")
        observer, _ = _candidate(client, f"observer-{uuid4().hex}")

        public_job = _create_job(client, owner_headers, "historically-public")
        public_job = _status(client, owner_headers, public_job, "open")
        with application.state.database.session_factory() as session:
            applicant_user = session.get(User, UUID(applicant["user_id"]))
            assert applicant_user is not None
            candidate = AtsCandidate(
                organization_id=UUID(public_job["organization_id"]),
                email=applicant_user.email,
                first_name=applicant_user.first_name,
                last_name=applicant_user.last_name,
                phone="+1 780 555 0199",
                status="active",
                created_by_user_id=UUID(owner["user"]["id"]),
                claimed_user_id=applicant_user.id,
                onboarding_status="complete",
                candidate_type="student",
                work_history=[],
            )
            session.add(candidate)
            session.flush()
            applied = AtsApplication(
                organization_id=UUID(public_job["organization_id"]),
                job_id=UUID(public_job["id"]),
                candidate_id=candidate.id,
                status="applied",
                source="marketplace_application",
                candidate_consent_status="accepted",
                version=1,
            )
            session.add(applied)
            session.flush()
            session.add(
                MarketplaceApplicationLink(
                    user_id=applicant_user.id,
                    organization_id=UUID(public_job["organization_id"]),
                    listing_id=UUID(public_job["id"]),
                    application_id=applied.id,
                    listing_title=public_job["title"],
                    organization_name="Historical Outbox Centre",
                    listing_location=public_job["location"],
                    employment_type=public_job["employment_type"],
                    published_at=datetime.fromisoformat(
                        public_job["published_at"].replace("Z", "+00:00")
                    ),
                )
            )
            session.commit()
        public_job = _status(client, owner_headers, public_job, "closed")

        never_public = _create_job(client, owner_headers, "never-public")
        never_public = _status(client, owner_headers, never_public, "closed")
        assert never_public["published_at"] is None
        assert client.get(f"/api/v1/marketplace/jobs/{public_job['id']}").status_code == 404

        with application.state.database.session_factory() as session:
            before_cursor = int(session.scalar(select(func.max(RealtimeEvent.sequence_id))) or 0)
            application_link = session.scalar(
                select(MarketplaceApplicationLink).where(
                    MarketplaceApplicationLink.user_id == UUID(applicant["user_id"])
                )
            )
            assert application_link is not None
            application_id = application_link.application_id
            listing_snapshot = (
                application_link.listing_title,
                application_link.organization_name,
                application_link.published_at,
            )
            assert session.get(MarketplaceJob, UUID(public_job["id"])) is None

    command.upgrade(config, CURRENT_REVISION)
    # This historical 0038 behavior proof still stops at the public-catalog
    # migration for its assertions.  Alembic's drift check, however, is only
    # valid at the repository head now that 0039 is additive above 0038.
    command.upgrade(config, "head")
    command.check(config)
    inspector = inspect(sa.create_engine(f"sqlite:///{database_path}"))
    try:
        assert {item["name"] for item in inspector.get_columns("public_job_catalog_events")} == {
            "sequence_id",
            "event_id",
            "listing_id",
            "event_type",
            "public_status",
            "listing_version",
            "occurred_at",
        }
    finally:
        inspector.bind.dispose()

    application = create_app(_settings(database_path))
    with TestClient(application) as client:
        with application.state.database.session_factory() as session:
            rows = list(
                session.scalars(
                    select(PublicJobCatalogEvent).order_by(PublicJobCatalogEvent.sequence_id)
                )
            )
            assert len(rows) == 1
            row = rows[0]
            assert row.listing_id == UUID(public_job["id"])
            assert row.event_type == "job.status_changed"
            assert row.public_status == "closed"
            assert row.listing_version == public_job["version"]
            assert row.sequence_id > before_cursor
            parent = session.get(RealtimeEvent, row.sequence_id)
            assert parent is not None
            assert parent.id == row.event_id
            assert parent.entity_id == row.listing_id
            assert parent.event_type == "job.status_changed"
            assert parent.payload == {
                "source": "0038_public_job_catalog_backfill",
                "refresh_required": True,
            }
            assert not any(item.listing_id == UUID(never_public["id"]) for item in rows)

            observer_id = UUID(observer["user_id"])
            assert session.scalar(
                select(func.count())
                .select_from(MarketplaceApplicationLink)
                .where(MarketplaceApplicationLink.user_id == observer_id)
            ) == 0
            assert session.scalar(
                select(func.count())
                .select_from(MarketplaceInterest)
                .where(MarketplaceInterest.profile_user_id == observer_id)
            ) == 0
            assert session.scalar(
                select(func.count())
                .select_from(OrganizationMembership)
                .where(OrganizationMembership.user_id == observer_id)
            ) == 0
            replay = _candidate_events(
                session,
                observer_id,
                before_cursor,
                100,
                public_catalog_enabled=True,
            )
            assert replay == [row]
            assert (
                _candidate_latest_cursor(
                    session,
                    observer_id,
                    public_catalog_enabled=True,
                )
                == row.sequence_id
            )
            assert _frame(row) == {
                "type": "event",
                "cursor": row.sequence_id,
                "event": {
                    "id": str(row.event_id),
                    "type": row.event_type,
                    "entity_type": "job",
                    "entity_id": str(row.listing_id),
                    "occurred_at": row.occurred_at.isoformat(),
                    "payload": {"scope": "candidate_hiring"},
                },
            }

            retained = session.scalar(
                select(MarketplaceApplicationLink).where(
                    MarketplaceApplicationLink.application_id == application_id
                )
            )
            assert retained is not None
            assert (
                retained.listing_title,
                retained.organization_name,
                retained.published_at,
            ) == listing_snapshot

        # A missing canonical projection is a successful invalidation outcome,
        # not permission to smuggle a stale listing copy into the event frame.
        assert client.get(f"/api/v1/marketplace/jobs/{public_job['id']}").status_code == 404
        history = client.get(
            "/api/v1/marketplace/applications",
            headers=applicant_headers,
        )
        assert history.status_code == 200, history.text
        assert history.json()[0]["job"]["id"] == public_job["id"]
        assert history.json()[0]["job"]["title"] == listing_snapshot[0]


def test_live_catalog_transitions_are_ordered_deduplicated_and_private_text_free(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, database_path = _config(tmp_path, monkeypatch)
    command.upgrade(config, CURRENT_REVISION)
    application = create_app(_settings(database_path))
    with TestClient(application) as client:
        _, owner_headers = _owner(client, uuid4().hex)
        observer, observer_headers = _candidate(
            client,
            f"live-observer-{uuid4().hex}",
        )
        job = _create_job(client, owner_headers, "DO-NOT-COPY")
        patched = client.patch(
            f"/api/v1/ats/jobs/{job['id']}",
            headers=owner_headers,
            json={
                "expected_version": job["version"],
                "title": "STILL-PRIVATE-TITLE",
                "description": "STILL-PRIVATE-DESCRIPTION",
            },
        )
        assert patched.status_code == 200, patched.text
        job = patched.json()
        with application.state.database.session_factory() as session:
            assert session.scalar(
                select(func.count()).select_from(PublicJobCatalogEvent)
            ) == 0

        job = _status(client, owner_headers, job, "open")
        with application.state.database.session_factory() as session:
            open_event = session.scalar(select(PublicJobCatalogEvent))
            assert open_event is not None
            disconnected_after = open_event.sequence_id

        public_edit = client.patch(
            f"/api/v1/ats/jobs/{job['id']}",
            headers=owner_headers,
            json={
                "expected_version": job["version"],
                "title": "PUBLIC-LATEST-TITLE",
                "description": "PUBLIC-LATEST-DESCRIPTION",
            },
        )
        assert public_edit.status_code == 200, public_edit.text
        job = public_edit.json()
        with application.state.database.session_factory() as session:
            edit_replay = _candidate_events(
                session,
                UUID(observer["user_id"]),
                disconnected_after,
                100,
                public_catalog_enabled=True,
            )
            assert len(edit_replay) == 1
            assert isinstance(edit_replay[0], PublicJobCatalogEvent)
            assert edit_replay[0].event_type == "job.updated"
            assert edit_replay[0].listing_version == job["version"]
        canonical = client.get(f"/api/v1/marketplace/jobs/{job['id']}")
        assert canonical.status_code == 200, canonical.text
        assert canonical.json()["title"] == "PUBLIC-LATEST-TITLE"
        assert canonical.json()["description"] == "PUBLIC-LATEST-DESCRIPTION"

        job = _status(client, owner_headers, job, "paused")
        paused_edit = client.patch(
            f"/api/v1/ats/jobs/{job['id']}",
            headers=owner_headers,
            json={
                "expected_version": job["version"],
                "title": "PAUSED-LATEST-TITLE",
                "description": "PAUSED-LATEST-DESCRIPTION",
            },
        )
        assert paused_edit.status_code == 200, paused_edit.text
        job = paused_edit.json()
        job = _status(client, owner_headers, job, "open")
        reopened = client.get(f"/api/v1/marketplace/jobs/{job['id']}")
        assert reopened.status_code == 200, reopened.text
        assert reopened.json()["title"] == "PAUSED-LATEST-TITLE"
        assert reopened.json()["description"] == "PAUSED-LATEST-DESCRIPTION"
        job = _status(client, owner_headers, job, "closed")

        never_public = _create_job(client, owner_headers, "NEVER-PUBLIC")
        _status(client, owner_headers, never_public, "closed")

        with application.state.database.session_factory() as session:
            rows = list(
                session.scalars(
                    select(PublicJobCatalogEvent).order_by(PublicJobCatalogEvent.sequence_id)
                )
            )
            assert [row.public_status for row in rows] == [
                "open",
                "open",
                "paused",
                "open",
                "closed",
            ]
            assert [row.event_type for row in rows] == [
                "job.status_changed",
                "job.updated",
                "job.status_changed",
                "job.status_changed",
                "job.status_changed",
            ]
            assert [row.listing_version for row in rows] == [3, 4, 5, 7, 8]
            assert [row.sequence_id for row in rows] == sorted(
                row.sequence_id for row in rows
            )
            assert len({row.event_id for row in rows}) == 5
            assert len({(row.listing_id, row.listing_version) for row in rows}) == 5
            assert {row.listing_id for row in rows} == {UUID(job["id"])}
            for row in rows:
                parent = session.get(RealtimeEvent, row.sequence_id)
                assert parent is not None
                assert (parent.id, parent.entity_id, parent.occurred_at) == (
                    row.event_id,
                    row.listing_id,
                    row.occurred_at,
                )
                assert set(_frame(row)["event"]) == {
                    "id",
                    "type",
                    "entity_type",
                    "entity_id",
                    "occurred_at",
                    "payload",
                }
                assert _frame(row)["event"]["payload"] == {"scope": "candidate_hiring"}

            observer_id = UUID(observer["user_id"])
            replay = _candidate_events(
                session,
                observer_id,
                rows[-2].sequence_id,
                100,
                public_catalog_enabled=True,
            )
            assert replay == [rows[-1]]
            assert (
                _candidate_latest_cursor(
                    session,
                    observer_id,
                    public_catalog_enabled=True,
                )
                == rows[-1].sequence_id
            )
            reopen_cursor = rows[-2].sequence_id
            close_cursor = rows[-1].sequence_id
            close_event_id = rows[-1].event_id

            session.add(
                RealtimeEvent(
                    organization_id=UUID(job["organization_id"]),
                    event_type="job.status_changed",
                    entity_type="job",
                    entity_id=UUID(job["id"]),
                    payload={
                        "title": "MUST-NOT-COPY",
                        "description": "MUST-NOT-COPY",
                    },
                )
            )
            with pytest.raises(IntegrityError):
                session.flush()
            session.rollback()
            assert session.scalar(
                select(func.count()).select_from(PublicJobCatalogEvent)
            ) == 5

        ticket = client.post(
            "/api/v1/marketplace/realtime/tickets",
            headers=observer_headers,
        )
        assert ticket.status_code == 201, ticket.text
        with client.websocket_connect(
            f"/api/v1/marketplace/realtime/ws?"
            f"ticket={ticket.json()['ticket']}&after={reopen_cursor}"
        ) as websocket:
            ready = websocket.receive_json()
            assert ready["type"] == "ready"
            assert ready["cursor_semantics"] == (
                "last_emitted_event; persist only after local refresh succeeds"
            )
            frame = websocket.receive_json()
            assert frame["cursor"] == close_cursor
            assert frame["event"] == {
                "id": str(close_event_id),
                "type": "job.status_changed",
                "entity_type": "job",
                "entity_id": job["id"],
                "occurred_at": frame["event"]["occurred_at"],
                "payload": {"scope": "candidate_hiring"},
            }

        assert client.get(f"/api/v1/marketplace/jobs/{job['id']}").status_code == 404


def test_downgrade_preserves_harmless_synthetic_realtime_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, database_path = _config(tmp_path, monkeypatch)
    command.upgrade(config, PREVIOUS_REVISION)
    application = create_app(_settings(database_path))
    with TestClient(application) as client:
        _, owner_headers = _owner(client, uuid4().hex)
        job = _status(
            client,
            owner_headers,
            _create_job(client, owner_headers, "downgrade-history"),
            "open",
        )

    command.upgrade(config, CURRENT_REVISION)
    engine = sa.create_engine(f"sqlite:///{database_path}")
    with Session(engine) as session:
        first_projection = session.scalar(select(PublicJobCatalogEvent))
        assert first_projection is not None
        first_backfill_event_id = first_projection.event_id
        first_parent = session.get(RealtimeEvent, first_projection.sequence_id)
        assert first_parent is not None
        assert first_parent.payload["source"] == "0038_public_job_catalog_backfill"

    command.downgrade(config, PREVIOUS_REVISION)
    assert "public_job_catalog_events" not in inspect(engine).get_table_names()
    with Session(engine) as session:
        retained_parent = session.scalar(
            select(RealtimeEvent).where(RealtimeEvent.id == first_backfill_event_id)
        )
        assert retained_parent is not None
        assert retained_parent.entity_id == UUID(job["id"])
        assert retained_parent.payload == {
            "source": "0038_public_job_catalog_backfill",
            "refresh_required": True,
        }

    command.upgrade(config, CURRENT_REVISION)
    with Session(engine) as session:
        second_projection = session.scalar(select(PublicJobCatalogEvent))
        assert second_projection is not None
        assert second_projection.event_id != first_backfill_event_id
        assert session.scalar(
            select(func.count())
            .select_from(RealtimeEvent)
            .where(
                RealtimeEvent.event_type == "job.status_changed",
                RealtimeEvent.entity_id == UUID(job["id"]),
            )
        ) >= 3
    engine.dispose()


@pytest.mark.skipif(
    not POSTGRES_OUTBOX_TEST_URL,
    reason=(
        "BASIC_POSTGRES_PUBLIC_JOB_OUTBOX_TEST_URL must name a disposable "
        "loopback PostgreSQL cluster"
    ),
)
def test_postgres_outbox_is_globally_readable_but_runtime_immutable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert POSTGRES_OUTBOX_TEST_URL is not None
    admin_url = make_url(POSTGRES_OUTBOX_TEST_URL)
    assert admin_url.get_backend_name() == "postgresql"
    assert admin_url.host in {"127.0.0.1", "localhost", "::1"}
    assert admin_url.port is not None
    assert admin_url.port not in {5432, 5433, 5434}
    assert admin_url.database == "postgres"
    assert admin_url.username
    database_name = f"caresync_public_outbox_{uuid4().hex[:10]}"
    database_url = admin_url.set(database=database_name)
    admin = sa.create_engine(admin_url, isolation_level="AUTOCOMMIT")
    database_engine = None
    try:
        with admin.connect() as connection:
            connection.execute(sa.text(f'CREATE DATABASE "{database_name}"'))
        monkeypatch.setenv("ENVIRONMENT", "test")
        config = Config(str(BACKEND_ROOT / "alembic.ini"))
        config.set_main_option(
            "sqlalchemy.url",
            database_url.render_as_string(hide_password=False).replace("%", "%%"),
        )
        command.upgrade(config, CURRENT_REVISION)
        database_engine = sa.create_engine(database_url)
        with database_engine.connect() as connection:
            row_security = connection.execute(
                sa.text(
                    "SELECT relrowsecurity,relforcerowsecurity "
                    "FROM pg_catalog.pg_class "
                    "WHERE oid='public.public_job_catalog_events'::regclass"
                )
            ).one()
            assert row_security.relrowsecurity is True
            assert row_security.relforcerowsecurity is False
            policies = set(
                connection.execute(
                    sa.text(
                        "SELECT policyname FROM pg_catalog.pg_policies "
                        "WHERE schemaname='public' "
                        "AND tablename='public_job_catalog_events'"
                    )
                ).scalars()
            )
            assert policies == {"public_job_catalog_events_public_read"}
            app_role_exists = bool(
                connection.scalar(
                    sa.text(
                        "SELECT EXISTS(SELECT 1 FROM pg_catalog.pg_roles "
                        "WHERE rolname='caresync_basic_app')"
                    )
                )
            )
            if app_role_exists:
                privileges = {
                    privilege: bool(
                        connection.scalar(
                            sa.text(
                                "SELECT pg_catalog.has_table_privilege("
                                "'caresync_basic_app','public.public_job_catalog_events',"
                                ":privilege)"
                            ),
                            {"privilege": privilege},
                        )
                    )
                    for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE")
                }
                assert privileges == {
                    "SELECT": True,
                    "INSERT": False,
                    "UPDATE": False,
                    "DELETE": False,
                    "TRUNCATE": False,
                }
            function = connection.execute(
                sa.text(
                    "SELECT prosecdef,proconfig FROM pg_catalog.pg_proc "
                    "WHERE oid='public.caresync_public_job_catalog_from_realtime()'"
                    "::regprocedure"
                )
            ).one()
            assert function.prosecdef is True
            assert "search_path=pg_catalog" in (function.proconfig or [])
    finally:
        if database_engine is not None:
            database_engine.dispose()
        with admin.connect() as connection:
            connection.execute(
                sa.text(
                    "SELECT pg_catalog.pg_terminate_backend(pid) "
                    "FROM pg_catalog.pg_stat_activity "
                    "WHERE datname=:database_name AND pid<>pg_catalog.pg_backend_pid()"
                ),
                {"database_name": database_name},
            )
            connection.execute(sa.text(f'DROP DATABASE IF EXISTS "{database_name}"'))
        admin.dispose()


@pytest.mark.skipif(
    not POSTGRES_OUTBOX_TEST_URL,
    reason=(
        "BASIC_POSTGRES_PUBLIC_JOB_OUTBOX_TEST_URL must name a disposable "
        "loopback PostgreSQL cluster"
    ),
)
def test_postgres_restricted_owner_backfill_and_runtime_trigger_behavior(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prove migration and live trigger behavior without superuser/BYPASSRLS shortcuts."""

    assert POSTGRES_OUTBOX_TEST_URL is not None
    admin_url = make_url(POSTGRES_OUTBOX_TEST_URL)
    assert admin_url.get_backend_name() == "postgresql"
    assert admin_url.host in {"127.0.0.1", "localhost", "::1"}
    assert admin_url.port is not None
    assert admin_url.port not in {5432, 5433, 5434}
    assert admin_url.database == "postgres"
    assert admin_url.username

    marker = uuid4().hex[:10]
    # Settings deliberately permits only the canonical database name. The
    # opt-in guard above restricts this test to an isolated nonstandard-port
    # cluster, and the finally block removes the disposable database.
    database_name = "caresync"
    owner_name = f"caresync_outbox_owner_{marker}"
    owner_password = f"Owner{uuid4().hex}"
    runtime_password = f"Runtime{uuid4().hex}"
    owner_url = admin_url.set(
        username=owner_name,
        password=owner_password,
        database=database_name,
    )
    runtime_url = admin_url.set(
        username="caresync_basic_app",
        password=runtime_password,
        database=database_name,
    )
    admin = sa.create_engine(admin_url, isolation_level="AUTOCOMMIT")
    admin_database_engine = None
    owner_engine = None
    runtime_engine = None
    runtime_namespace_owned = False
    try:
        with admin.connect() as connection:
            existing_runtime_roles = connection.scalar(
                sa.text(
                    "SELECT count(*) FROM pg_catalog.pg_roles "
                    "WHERE rolname=ANY(CAST(:roles AS text[]))"
                ),
                {"roles": list(POSTGRES_RUNTIME_ROLES)},
            )
            assert existing_runtime_roles == 0, (
                "The public-outbox runtime role namespace must be fresh"
            )
            runtime_namespace_owned = True
            connection.exec_driver_sql(
                f'CREATE ROLE "{owner_name}" LOGIN NOSUPERUSER NOCREATEDB '
                "NOCREATEROLE NOREPLICATION NOINHERIT NOBYPASSRLS "
                f"PASSWORD '{owner_password}'"
            )
            connection.exec_driver_sql(
                f'CREATE DATABASE "{database_name}" OWNER "{owner_name}"'
            )

        monkeypatch.setenv("ENVIRONMENT", "test")
        config = Config(str(BACKEND_ROOT / "alembic.ini"))
        config.set_main_option(
            "sqlalchemy.url",
            owner_url.render_as_string(hide_password=False).replace("%", "%%"),
        )
        command.upgrade(config, PREVIOUS_REVISION)
        owner_engine = sa.create_engine(owner_url)
        with owner_engine.connect() as connection:
            role = connection.execute(
                sa.text(
                    "SELECT rolsuper,rolbypassrls,rolinherit,rolcreaterole,"
                    "rolcreatedb,rolreplication FROM pg_catalog.pg_roles "
                    "WHERE rolname=current_user"
                )
            ).one()
            assert tuple(role) == (False, False, False, False, False, False)

        historical_organization_id = uuid4()
        historical_user_id = uuid4()
        historical_job_id = uuid4()
        with owner_engine.begin() as connection:
            for table in ("users", "organizations", "ats_jobs"):
                connection.exec_driver_sql(
                    f"ALTER TABLE public.{table} NO FORCE ROW LEVEL SECURITY"
                )
        with Session(owner_engine) as session:
            session.add_all(
                [
                    User(
                        id=historical_user_id,
                        email=f"historical-{marker}@example.test",
                        password_hash="not-used",
                        first_name="Historical",
                        last_name="Owner",
                    ),
                    Organization(
                        id=historical_organization_id,
                        name=f"Historical Centre {marker}",
                        status="active",
                    ),
                ]
            )
            session.flush()
            session.add(
                AtsJob(
                    id=historical_job_id,
                    organization_id=historical_organization_id,
                    title="Historical public listing",
                    description="Backfill source",
                    employment_type="full_time",
                    location="Edmonton",
                    requirements=[],
                    openings=1,
                    status="open",
                    published_at=datetime.now(UTC),
                    created_by_user_id=historical_user_id,
                    version=7,
                )
            )
            session.commit()
        with owner_engine.begin() as connection:
            for table in ("users", "organizations", "ats_jobs"):
                connection.exec_driver_sql(
                    f"ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY"
                )

        command.upgrade(config, CURRENT_REVISION)
        # The assertions above deliberately exercise the restricted-owner
        # 0038 transition. Alembic's drift check is meaningful only after the
        # same disposable database reaches the repository head.
        command.upgrade(config, "head")
        command.check(config)
        with owner_engine.connect() as connection:
            force_state = dict(
                connection.execute(
                    sa.text(
                        "SELECT relation.relname,relation.relforcerowsecurity "
                        "FROM pg_catalog.pg_class AS relation "
                        "JOIN pg_catalog.pg_namespace AS namespace "
                        "ON namespace.oid=relation.relnamespace "
                        "WHERE namespace.nspname='public' "
                        "AND relation.relname IN ('ats_jobs','realtime_events')"
                    )
                ).tuples().all()
            )
            assert force_state == {"ats_jobs": True, "realtime_events": True}
            backfill = connection.execute(
                sa.text(
                    "SELECT listing_id,event_type,public_status,listing_version "
                    "FROM public.public_job_catalog_events "
                    "WHERE listing_id=:listing_id"
                ),
                {"listing_id": historical_job_id},
            ).one()
            assert tuple(backfill) == (
                historical_job_id,
                "job.status_changed",
                "open",
                7,
            )

        # The historical 0033 attestation writer is intentionally certified as
        # a BYPASSRLS SECURITY DEFINER guard. Running the whole lineage under
        # this test's restricted 0038 owner would leave that older function in
        # a topology production startup correctly rejects. Restore its
        # production owner without changing ownership of any 0038 object.
        admin_database_engine = sa.create_engine(
            admin_url.set(database=database_name)
        )
        with admin_database_engine.begin() as connection:
            connection.exec_driver_sql(
                "ALTER FUNCTION "
                "public.caresync_0033_attested_source_immutable() "
                f'OWNER TO "{admin_url.username}"'
            )

        _run_bootstrap(admin_url, database_name)
        with admin.connect() as connection:
            connection.exec_driver_sql(
                "ALTER ROLE caresync_basic_app "
                f"PASSWORD '{runtime_password}'"
            )

        application = create_app(_postgres_settings(runtime_url))
        with TestClient(application) as client:
            assert application.state.public_job_catalog_outbox_enabled is True
            owner, owner_headers = _owner(client, f"postgres-{marker}")
            observer, _ = _candidate(client, f"postgres-observer-{marker}")
            job = _create_job(client, owner_headers, f"postgres-{marker}")
            job = _status(client, owner_headers, job, "open")
            edited = client.patch(
                f"/api/v1/ats/jobs/{job['id']}",
                headers=owner_headers,
                json={
                    "expected_version": job["version"],
                    "title": "Canonical latest title",
                    "description": "Canonical latest description",
                },
            )
            assert edited.status_code == 200, edited.text
            job = edited.json()
            job = _status(client, owner_headers, job, "paused")
            job = _status(client, owner_headers, job, "closed")

            with application.state.database.session_factory() as session:
                owner_user_id = UUID(owner["user"]["id"])
                organization_id = UUID(job["organization_id"])
                set_rls_user(session, owner_user_id)
                set_rls_organization(session, organization_id)
                rows = list(
                    session.scalars(
                        select(PublicJobCatalogEvent)
                        .where(PublicJobCatalogEvent.listing_id == UUID(job["id"]))
                        .order_by(PublicJobCatalogEvent.sequence_id)
                    )
                )
                assert [
                    (row.event_type, row.public_status, row.listing_version)
                    for row in rows
                ] == [
                    ("job.status_changed", "open", 2),
                    ("job.updated", "open", 3),
                    ("job.status_changed", "paused", 4),
                    ("job.status_changed", "closed", 5),
                ]
                for row in rows:
                    parent = session.get(RealtimeEvent, row.sequence_id)
                    assert parent is not None
                    assert (parent.id, parent.entity_id, parent.occurred_at) == (
                        row.event_id,
                        row.listing_id,
                        row.occurred_at,
                    )

                observer_id = UUID(observer["user_id"])
                replay = _candidate_events(
                    session,
                    observer_id,
                    rows[0].sequence_id - 1,
                    100,
                    public_catalog_enabled=True,
                )
                listing_replay = [
                    event
                    for event in replay
                    if isinstance(event, PublicJobCatalogEvent)
                    and event.listing_id == UUID(job["id"])
                ]
                assert listing_replay == rows
                frames = [_frame(event) for event in listing_replay]
                assert all(
                    frame["event"]["payload"] == {"scope": "candidate_hiring"}
                    and set(frame["event"]) == {
                        "id",
                        "type",
                        "entity_type",
                        "entity_id",
                        "occurred_at",
                        "payload",
                    }
                    for frame in frames
                )

                set_rls_user(session, owner_user_id)
                set_rls_organization(session, organization_id)
                duplicate_parent_id = uuid4()
                parent_count = int(
                    session.scalar(
                        select(func.count()).select_from(RealtimeEvent)
                    )
                    or 0
                )
                session.add(
                    RealtimeEvent(
                        id=duplicate_parent_id,
                        organization_id=UUID(job["organization_id"]),
                        event_type="job.status_changed",
                        entity_type="job",
                        entity_id=UUID(job["id"]),
                        payload={"must_rollback": True},
                    )
                )
                with pytest.raises(IntegrityError):
                    session.commit()
                session.rollback()
                set_rls_user(session, owner_user_id)
                set_rls_organization(session, organization_id)
                assert session.scalar(
                    select(func.count())
                    .select_from(RealtimeEvent)
                    .where(RealtimeEvent.id == duplicate_parent_id)
                ) == 0
                assert int(
                    session.scalar(
                        select(func.count()).select_from(RealtimeEvent)
                    )
                    or 0
                ) == parent_count

            assert client.get(f"/api/v1/marketplace/jobs/{job['id']}").status_code == 404

        runtime_engine = sa.create_engine(runtime_url)
        with runtime_engine.connect() as connection:
            assert connection.scalar(
                sa.text(
                    "SELECT count(*) FROM public.public_job_catalog_events "
                    "WHERE listing_id=:listing_id"
                ),
                {"listing_id": UUID(job["id"])},
            ) == 4
            with pytest.raises(DBAPIError):
                connection.execute(
                    sa.text(
                        "DELETE FROM public.public_job_catalog_events "
                        "WHERE listing_id=:listing_id"
                    ),
                    {"listing_id": UUID(job["id"])},
                )
    finally:
        if runtime_engine is not None:
            runtime_engine.dispose()
        if owner_engine is not None:
            owner_engine.dispose()
        if admin_database_engine is not None:
            admin_database_engine.dispose()
        with admin.connect() as connection:
            connection.execute(
                sa.text(
                    "SELECT pg_catalog.pg_terminate_backend(pid) "
                    "FROM pg_catalog.pg_stat_activity "
                    "WHERE datname=:database_name AND pid<>pg_catalog.pg_backend_pid()"
                ),
                {"database_name": database_name},
            )
            connection.exec_driver_sql(
                f'DROP DATABASE IF EXISTS "{database_name}"'
            )
            if runtime_namespace_owned:
                for role_name in POSTGRES_RUNTIME_ROLES:
                    connection.exec_driver_sql(f'DROP ROLE IF EXISTS "{role_name}"')
            connection.exec_driver_sql(f'DROP ROLE IF EXISTS "{owner_name}"')
        admin.dispose()
