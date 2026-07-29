"""Portable 0032 command, exact-retry, and fail-closed capability proofs."""

from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from alembic.config import Config
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from alembic import command
from app.api.basic.dependencies import BasicContext
from app.api.basic.staff_operations import _driver_registry_capability
from app.basic.models import (
    Organization,
    OrganizationMembership,
    RealtimeEvent,
    Role,
    StaffDriverQualificationReviewDecision,
    StaffDriverQualificationVersion,
    StaffDriverReadinessDecision,
    TransportRegistryCommandReceipt,
    TransportVehicle,
    TransportVehicleVersion,
    User,
    UserNotification,
)
from app.basic.security import hash_password
from app.basic.transport_registry_commands import _organization_date, execute_transport_command
from app.core.config import Settings
from app.db.sqlite_functions import caresync_local_date
from app.main import create_app

BACKEND_ROOT = Path(__file__).resolve().parents[1]
ALBERTA_TIMEZONE = ZoneInfo("America/Edmonton")


def _alberta_today() -> date:
    return datetime.now(ALBERTA_TIMEZONE).date()


def _settings(database_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        database_type="sqlite",
        database_path=database_path,
        database_name="caresync",
        database_read_only=False,
        enable_advanced_routes=False,
        jwt_secret="transport-command-test-secret-with-at-least-thirty-two-bytes",
    )


def _migrate(tmp_path: Path, monkeypatch, revision: str = "head") -> Path:
    database_path = tmp_path / "caresync.db"
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DATABASE_TYPE", "sqlite")
    monkeypatch.setenv("DATABASE_PATH", str(database_path))
    monkeypatch.setenv("DATABASE_NAME", "caresync")
    monkeypatch.setenv("DATABASE_READ_ONLY", "false")
    command.upgrade(Config(str(BACKEND_ROOT / "alembic.ini")), revision)
    return database_path


def _sqlite_trigger_bodies(database_path: Path, *names: str) -> dict[str, str]:
    with sqlite3.connect(database_path) as connection:
        return {
            name: sql
            for name, sql in connection.execute(
                "SELECT name,sql FROM sqlite_master WHERE type='trigger' "
                f"AND name IN ({','.join('?' for _ in names)}) ORDER BY name",
                names,
            )
        }


def test_0032_converges_experimental_0031_guards_to_fresh_head(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """An already-stamped experimental 0031 gets the exact fresh-head guards."""
    guarded_names = (
        "staff_driver_authorization_insert_guard",
        "transport_vehicle_versions_plate_guard",
    )

    fresh_dir = tmp_path / "fresh"
    fresh_dir.mkdir()
    fresh_path = _migrate(fresh_dir, monkeypatch)
    fresh_bodies = _sqlite_trigger_bodies(fresh_path, *guarded_names)

    upgrade_dir = tmp_path / "upgrade"
    upgrade_dir.mkdir()
    upgrade_path = _migrate(
        upgrade_dir,
        monkeypatch,
        revision="0031_driver_vehicle_registry",
    )
    hardened_0031_bodies = _sqlite_trigger_bodies(upgrade_path, *guarded_names)
    assert hardened_0031_bodies == fresh_bodies
    with sqlite3.connect(upgrade_path) as connection:
        for name in guarded_names:
            connection.execute(f"DROP TRIGGER {name}")
        connection.execute(
            "CREATE TRIGGER staff_driver_authorization_insert_guard BEFORE INSERT ON "
            "staff_driver_authorization_decisions WHEN 0 BEGIN SELECT 1; END"
        )
        connection.execute(
            "CREATE TRIGGER transport_vehicle_versions_plate_guard BEFORE INSERT ON "
            "transport_vehicle_versions WHEN 0 BEGIN SELECT 1; END"
        )

    command.upgrade(Config(str(BACKEND_ROOT / "alembic.ini")), "head")
    upgraded_bodies = _sqlite_trigger_bodies(upgrade_path, *guarded_names)

    assert upgraded_bodies == fresh_bodies
    assert set(upgraded_bodies) == set(guarded_names)
    assert "caresync_local_date" in upgraded_bodies["staff_driver_authorization_insert_guard"]
    assert (
        "current_qualification.version_number"
        in upgraded_bodies["staff_driver_authorization_insert_guard"]
    )
    assert "WITH RECURSIVE normalized" in upgraded_bodies["transport_vehicle_versions_plate_guard"]


@pytest.mark.parametrize(
    ("plates", "marker"),
    [
        (("--",), "empty normalized plate"),
        (("ABC 123", "a-b.c_123"), "duplicate normalized active vehicle plate"),
    ],
)
def test_0032_refuses_legacy_0031_active_plate_drift_without_mutation(
    tmp_path: Path,
    monkeypatch,
    plates: tuple[str, ...],
    marker: str,
) -> None:
    database_path = _migrate(
        tmp_path,
        monkeypatch,
        revision="0031_driver_vehicle_registry",
    )
    application = create_app(_settings(database_path))
    with TestClient(application) as client:
        _register(client)
        with sqlite3.connect(database_path) as connection:
            connection.execute("DROP TRIGGER transport_vehicle_versions_plate_guard")
        with application.state.database.session_factory() as session:
            context = _context(session, "transport-staff@example.test")
            now = datetime.now(UTC)
            for plate in plates:
                vehicle = TransportVehicle(
                    organization_id=context.organization.id,
                    owner_kind="staff_personal",
                    staff_owner_membership_id=context.membership.id,
                    created_by_user_id=context.user.id,
                    created_at=now,
                )
                session.add(vehicle)
                session.flush()
                session.add(
                    TransportVehicleVersion(
                        organization_id=context.organization.id,
                        vehicle_id=vehicle.id,
                        version_number=1,
                        make="Legacy",
                        model="Fixture",
                        model_year=2024,
                        color=None,
                        plate_token=plate,
                        plate_jurisdiction="CA-AB",
                        passenger_capacity=7,
                        child_passenger_capacity=6,
                        wheelchair_accessible=False,
                        effective_at=now,
                        recorded_by_user_id=context.user.id,
                        recorded_at=now,
                    )
                )
            session.commit()
    application.state.database.dispose()

    with pytest.raises(RuntimeError, match=marker):
        command.upgrade(Config(str(BACKEND_ROOT / "alembic.ini")), "head")

    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "0031_driver_vehicle_registry",
        )
        assert connection.execute("SELECT count(*) FROM transport_vehicles").fetchone() == (
            len(plates),
        )
        assert connection.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table' "
            "AND name='transport_registry_command_receipts'"
        ).fetchone() == (0,)


def _register(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "transport-staff@example.test",
            "password": "secure-password-123",
            "first_name": "Transport",
            "last_name": "Staff",
            "organization_name": "Transport Command Centre",
        },
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _context(session, email: str) -> BasicContext:
    user = session.query(User).filter_by(email=email).one()
    membership = session.query(OrganizationMembership).filter_by(user_id=user.id).one()
    organization = session.get(Organization, membership.organization_id)
    role = session.get(Role, membership.role_id)
    return BasicContext(
        user=user,
        organization=organization,
        membership=membership,
        role=role,
    )


def _reviewer(session, source: BasicContext) -> BasicContext:
    user = User(
        email="transport-reviewer@example.test",
        password_hash=hash_password("secure-password-456"),
        first_name="Independent",
        last_name="Reviewer",
        is_active=True,
        email_verified_at=datetime.now(UTC),
        email_verification_method="development_auto_verify",
    )
    session.add(user)
    session.flush()
    membership = OrganizationMembership(
        organization_id=source.organization.id,
        user_id=user.id,
        role_id=source.role.id,
        status="active",
        joined_at=datetime.now(UTC),
    )
    session.add(membership)
    session.commit()
    return BasicContext(
        user=user,
        organization=source.organization,
        membership=membership,
        role=source.role,
    )


def _evidence_private(
    now: datetime,
    *,
    actor_user_id: UUID,
    document_id: UUID,
    digest: str = "a" * 64,
) -> dict:
    return {
        "original_filename": "driver-licence.pdf",
        "media_type": "application/pdf",
        "byte_size": 2048,
        "content_sha256": digest,
        "ciphertext_sha256": "b" * 64,
        "storage_reference": (f"{actor_user_id.hex}/{document_id.hex}/{uuid4().hex}/v1.enc"),
        "encryption_key_id": "test-key-v1",
        "scanner_engine": "portable-test-scanner",
        "scanner_version": "1.0.0",
        "scanned_at": now.isoformat(),
    }


def test_capability_markers_keep_exact_legacy_and_0032_shapes():
    base_state = {
        "driver_vehicle_registry_enabled": False,
        "transport_registry_commands_enabled": False,
        "transport_registry_evidence_ingest_available": False,
        "transport_registry_evidence_pipeline_available": False,
        "transport_evidence_session_factory": None,
    }

    def marker(**changes):
        state = SimpleNamespace(**{**base_state, **changes})
        return _driver_registry_capability(SimpleNamespace(app=SimpleNamespace(state=state)))

    unavailable = marker()
    assert unavailable == {
        "schema_version": None,
        "runtime_available": False,
        "self_service_available": False,
        "read_path": None,
        "operational_driver_ready": False,
        "dispatch_authorized": False,
    }
    read_only = marker(driver_vehicle_registry_enabled=True)
    assert read_only == {
        "schema_version": "0031",
        "runtime_available": True,
        "self_service_available": True,
        "read_path": "/api/v1/staff/self/transport-registry",
        "operational_driver_ready": False,
        "dispatch_authorized": False,
    }
    commands = marker(
        driver_vehicle_registry_enabled=True,
        transport_registry_commands_enabled=True,
        transport_registry_evidence_ingest_available=True,
        transport_registry_evidence_pipeline_available=True,
        transport_evidence_session_factory=object(),
    )
    assert commands == {
        "schema_version": "0032",
        "runtime_available": True,
        "self_service_available": True,
        "read_path": "/api/v1/staff/self/transport-registry",
        "declaration_path": "/api/v1/staff/self/transport-registry/declarations",
        "qualification_evidence_path": (
            "/api/v1/staff/self/transport-registry/qualification-evidence"
        ),
        "personal_vehicle_path": "/api/v1/staff/self/transport-registry/vehicles",
        "vehicle_version_path_template": (
            "/api/v1/staff/self/transport-registry/vehicles/{vehicle_id}/versions"
        ),
        "vehicle_retirement_path_template": (
            "/api/v1/staff/self/transport-registry/vehicles/{vehicle_id}/retire"
        ),
        "vehicle_evidence_path_template": (
            "/api/v1/staff/self/transport-registry/vehicles/{vehicle_id}/evidence"
        ),
        "evidence_upload_available": True,
        "operational_driver_ready": False,
        "dispatch_authorized": False,
    }


@pytest.mark.parametrize(
    ("instant", "expected"),
    [
        (datetime(2026, 7, 22, 5, 0, tzinfo=UTC), date(2026, 7, 21)),
        (datetime(2026, 7, 22, 6, 0, tzinfo=UTC), date(2026, 7, 22)),
        (datetime(2026, 1, 22, 6, 0, tzinfo=UTC), date(2026, 1, 21)),
        (datetime(2026, 1, 22, 7, 0, tzinfo=UTC), date(2026, 1, 22)),
    ],
)
def test_organization_date_uses_edmonton_dst_boundary(instant, expected):
    context = SimpleNamespace(organization=SimpleNamespace(timezone="America/Edmonton"))
    assert _organization_date(context, instant) == expected


def test_organization_date_fails_closed_for_invalid_timezone():
    context = SimpleNamespace(organization=SimpleNamespace(timezone="Not/A-Timezone"))
    with pytest.raises(HTTPException) as error:
        _organization_date(context, datetime.now(UTC))
    assert error.value.detail == {"code": "organization_timezone_invalid"}


def test_sqlite_local_date_accepts_offset_input_and_utc_storage_contract():
    assert caresync_local_date("2026-07-22T07:30:00+02:00", "America/Edmonton") == "2026-07-21"
    assert caresync_local_date("2026-07-22 05:30:00", "America/Edmonton") == "2026-07-21"


def test_sqlite_http_commands_are_never_advertised_or_exposed(tmp_path, monkeypatch):
    database_path = _migrate(tmp_path, monkeypatch)
    application = create_app(_settings(database_path))
    with TestClient(application) as client:
        headers = _register(client)
        marker = client.get("/api/v1/staff/self", headers=headers).json()["driver_vehicle_registry"]
        assert marker["schema_version"] == "0031"
        operation_id = uuid4()
        response = client.post(
            "/api/v1/staff/self/transport-registry/declarations",
            headers=headers,
            json={
                "operation_id": str(operation_id),
                "status": "withdrawn",
                "willing_to_drive": False,
                "licence_jurisdiction": None,
                "licence_jurisdiction_other": None,
                "licence_class": None,
                "vehicle_access": "none",
                "preferred_service_radius_km": None,
            },
        )
        assert response.status_code == 503
        assert response.json()["detail"] == {"code": "transport_registry_commands_unavailable"}


def test_exact_retry_and_independent_review_are_bound_atomically(tmp_path, monkeypatch):
    database_path = _migrate(tmp_path, monkeypatch)
    application = create_app(_settings(database_path))
    with TestClient(application) as client:
        _register(client)
        with application.state.database.session_factory() as session:
            staff = _context(session, "transport-staff@example.test")
            reviewer = _reviewer(session, staff)
            declaration_operation = uuid4()
            declaration_payload = {
                "membership_id": str(staff.membership.id),
                "status": "declared",
                "willing_to_drive": True,
                "licence_jurisdiction": "CA-AB",
                "licence_jurisdiction_other": None,
                "licence_class": "5",
                "vehicle_access": "personal_vehicle",
                "preferred_service_radius_km": 30,
            }
            first = execute_transport_command(
                session=session,
                context=staff,
                command_kind="driver_declaration",
                operation_id=declaration_operation,
                public_payload=declaration_payload,
            )
            assert first.exact_retry is False
            replay = execute_transport_command(
                session=session,
                context=staff,
                command_kind="driver_declaration",
                operation_id=declaration_operation,
                public_payload=declaration_payload,
            )
            assert replay.exact_retry is True
            assert replay.result_id == first.result_id
            public_events = (
                session.query(RealtimeEvent)
                .filter_by(
                    organization_id=staff.organization.id,
                    event_type="transport_registry.changed",
                )
                .all()
            )
            assert len(public_events) == 1
            assert public_events[0].entity_type == "transport_registry"
            assert public_events[0].entity_id is None
            assert public_events[0].payload == {
                "source": "audit_event",
                "refresh_required": True,
            }
            assert str(first.result_id) not in str(public_events[0].payload)
            assert str(declaration_operation) not in str(public_events[0].payload)
            reviewer_capability = execute_transport_command(
                session=session,
                context=reviewer,
                command_kind="driver_declaration",
                operation_id=uuid4(),
                public_payload={
                    **declaration_payload,
                    "membership_id": str(reviewer.membership.id),
                },
            )
            with pytest.raises(HTTPException) as foreign_capability:
                execute_transport_command(
                    session=session,
                    context=reviewer,
                    command_kind="driver_authorization",
                    operation_id=uuid4(),
                    public_payload={
                        "membership_id": str(staff.membership.id),
                        "capability_version_id": str(reviewer_capability.result_id),
                        "qualification_version_ids": [],
                        "decision": "needs_review",
                        "reason_code": "foreign_capability_must_fail",
                        "authorization_valid_from": None,
                        "authorization_valid_until": None,
                    },
                )
            assert foreign_capability.value.detail == {"code": "authorization_capability_mismatch"}
            with pytest.raises(HTTPException, match="Independent authorization"):
                execute_transport_command(
                    session=session,
                    context=staff,
                    command_kind="driver_authorization",
                    operation_id=uuid4(),
                    public_payload={
                        "membership_id": str(staff.membership.id),
                        "capability_version_id": str(first.result_id),
                        "qualification_version_ids": [str(uuid4())],
                        "decision": "needs_review",
                        "reason_code": "self_review_forbidden",
                        "authorization_valid_from": None,
                        "authorization_valid_until": None,
                    },
                )
            with pytest.raises(HTTPException, match="Independent readiness"):
                execute_transport_command(
                    session=session,
                    context=staff,
                    command_kind="readiness_evaluation",
                    operation_id=uuid4(),
                    public_payload={
                        "membership_id": str(staff.membership.id),
                        "vehicle_id": None,
                    },
                )
            with pytest.raises(HTTPException, match="different command"):
                execute_transport_command(
                    session=session,
                    context=staff,
                    command_kind="driver_declaration",
                    operation_id=declaration_operation,
                    public_payload={**declaration_payload, "preferred_service_radius_km": 31},
                )

            now = datetime.now(UTC).replace(microsecond=0)
            with pytest.raises(HTTPException, match="conflicts with current facts"):
                execute_transport_command(
                    session=session,
                    context=staff,
                    command_kind="qualification_evidence",
                    operation_id=uuid4(),
                    public_payload={
                        "membership_id": str(staff.membership.id),
                        "qualification_type": "driver_licence",
                        "jurisdiction": "CA-AB",
                        "qualification_class": "5",
                        "identifier_last4": "9876",
                        "issue_date": (_alberta_today() - timedelta(days=300)).isoformat(),
                        "expiry_date": (_alberta_today() + timedelta(days=20)).isoformat(),
                        **_evidence_private(
                            now,
                            actor_user_id=reviewer.user.id,
                            document_id=staff.membership.id,
                        ),
                    },
                )
            evidence = execute_transport_command(
                session=session,
                context=staff,
                command_kind="qualification_evidence",
                operation_id=uuid4(),
                public_payload={
                    "membership_id": str(staff.membership.id),
                    "qualification_type": "driver_licence",
                    "jurisdiction": "CA-AB",
                    "qualification_class": "5",
                    "identifier_last4": "9876",
                    "issue_date": (_alberta_today() - timedelta(days=300)).isoformat(),
                    "expiry_date": (_alberta_today() + timedelta(days=20)).isoformat(),
                    **_evidence_private(
                        now,
                        actor_user_id=staff.user.id,
                        document_id=staff.membership.id,
                    ),
                },
            )
            with pytest.raises(HTTPException, match="Independent source evidence"):
                execute_transport_command(
                    session=session,
                    context=staff,
                    command_kind="qualification_review",
                    operation_id=uuid4(),
                    public_payload={
                        "membership_id": str(staff.membership.id),
                        "source_qualification_version_id": str(evidence.result_id),
                        "decision": "verified",
                        "reason_code": "evidence_reviewed",
                    },
                )
            review = execute_transport_command(
                session=session,
                context=reviewer,
                command_kind="qualification_review",
                operation_id=uuid4(),
                public_payload={
                    "membership_id": str(staff.membership.id),
                    "source_qualification_version_id": str(evidence.result_id),
                    "decision": "verified",
                    "reason_code": "evidence_reviewed",
                },
            )
            verified = session.get(StaffDriverQualificationVersion, review.result_id)
            assert verified.status == "verified"
            receipt = (
                session.query(TransportRegistryCommandReceipt)
                .filter_by(result_id=review.result_id)
                .one()
            )
            assert receipt.actor_user_id == reviewer.user.id
            assert receipt.operational_driver_ready is False
            assert receipt.dispatch_authorized is False

            stale_source = execute_transport_command(
                session=session,
                context=staff,
                command_kind="qualification_evidence",
                operation_id=uuid4(),
                public_payload={
                    "membership_id": str(staff.membership.id),
                    "qualification_type": "first_aid",
                    "jurisdiction": "CA-AB",
                    "qualification_class": None,
                    "identifier_last4": None,
                    "issue_date": _alberta_today().isoformat(),
                    "expiry_date": None,
                    **_evidence_private(
                        now,
                        actor_user_id=staff.user.id,
                        document_id=staff.membership.id,
                        digest="d" * 64,
                    ),
                },
            )
            execute_transport_command(
                session=session,
                context=staff,
                command_kind="qualification_evidence",
                operation_id=uuid4(),
                public_payload={
                    "membership_id": str(staff.membership.id),
                    "qualification_type": "first_aid",
                    "jurisdiction": "CA-AB",
                    "qualification_class": None,
                    "identifier_last4": None,
                    "issue_date": _alberta_today().isoformat(),
                    "expiry_date": None,
                    **_evidence_private(
                        now,
                        actor_user_id=staff.user.id,
                        document_id=staff.membership.id,
                        digest="e" * 64,
                    ),
                },
            )
            with pytest.raises(HTTPException, match="Independent source evidence"):
                execute_transport_command(
                    session=session,
                    context=reviewer,
                    command_kind="qualification_review",
                    operation_id=uuid4(),
                    public_payload={
                        "membership_id": str(staff.membership.id),
                        "source_qualification_version_id": str(stale_source.result_id),
                        "decision": "verified",
                        "reason_code": "stale_source_must_not_resurrect",
                    },
                )

            execute_transport_command(
                session=session,
                context=staff,
                command_kind="qualification_evidence",
                operation_id=uuid4(),
                public_payload={
                    "membership_id": str(staff.membership.id),
                    "qualification_type": "driver_licence",
                    "jurisdiction": "CA-AB",
                    "qualification_class": "5",
                    "identifier_last4": "9876",
                    "issue_date": (_alberta_today() - timedelta(days=300)).isoformat(),
                    "expiry_date": (_alberta_today() + timedelta(days=40)).isoformat(),
                    **_evidence_private(
                        now,
                        actor_user_id=staff.user.id,
                        document_id=staff.membership.id,
                        digest="f" * 64,
                    ),
                },
            )
            session.add(
                StaffDriverQualificationReviewDecision(
                    id=uuid4(),
                    organization_id=staff.organization.id,
                    membership_id=staff.membership.id,
                    source_qualification_version_id=evidence.result_id,
                    result_qualification_version_id=verified.id,
                    decision="verified",
                    reason_code="non_latest_result_must_fail",
                    reviewed_by_user_id=reviewer.user.id,
                    reviewed_at=now,
                    operational_driver_ready=False,
                    dispatch_authorized=False,
                )
            )
            with pytest.raises(IntegrityError, match="not independently evidence-bound"):
                session.flush()
            session.rollback()


def test_readiness_expiry_notification_names_the_actual_lane(tmp_path, monkeypatch):
    database_path = _migrate(tmp_path, monkeypatch)
    application = create_app(_settings(database_path))
    with TestClient(application) as client:
        _register(client)
        with application.state.database.session_factory() as session:
            staff = _context(session, "transport-staff@example.test")
            reviewer = _reviewer(session, staff)
            capability = execute_transport_command(
                session=session,
                context=staff,
                command_kind="driver_declaration",
                operation_id=uuid4(),
                public_payload={
                    "membership_id": str(staff.membership.id),
                    "status": "declared",
                    "willing_to_drive": True,
                    "licence_jurisdiction": "CA-AB",
                    "licence_jurisdiction_other": None,
                    "licence_class": "5",
                    "vehicle_access": "organization_vehicle_only",
                    "preferred_service_radius_km": 20,
                },
            )
            now = datetime.now(UTC).replace(microsecond=0)
            declared = execute_transport_command(
                session=session,
                context=staff,
                command_kind="qualification_evidence",
                operation_id=uuid4(),
                public_payload={
                    "membership_id": str(staff.membership.id),
                    "qualification_type": "driver_licence",
                    "jurisdiction": "CA-AB",
                    "qualification_class": "5",
                    "identifier_last4": "1234",
                    "issue_date": (_alberta_today() - timedelta(days=300)).isoformat(),
                    "expiry_date": (_alberta_today() + timedelta(days=20)).isoformat(),
                    **_evidence_private(
                        now,
                        actor_user_id=staff.user.id,
                        document_id=staff.membership.id,
                        digest="c" * 64,
                    ),
                },
            )
            verified = execute_transport_command(
                session=session,
                context=reviewer,
                command_kind="qualification_review",
                operation_id=uuid4(),
                public_payload={
                    "membership_id": str(staff.membership.id),
                    "source_qualification_version_id": str(declared.result_id),
                    "decision": "verified",
                    "reason_code": "licence_reviewed",
                },
            )
            first_aid_declared = execute_transport_command(
                session=session,
                context=staff,
                command_kind="qualification_evidence",
                operation_id=uuid4(),
                public_payload={
                    "membership_id": str(staff.membership.id),
                    "qualification_type": "first_aid",
                    "jurisdiction": "CA-AB",
                    "qualification_class": None,
                    "identifier_last4": None,
                    "issue_date": (_alberta_today() - timedelta(days=30)).isoformat(),
                    "expiry_date": (_alberta_today() + timedelta(days=200)).isoformat(),
                    **_evidence_private(
                        now,
                        actor_user_id=staff.user.id,
                        document_id=staff.membership.id,
                        digest="d" * 64,
                    ),
                },
            )
            first_aid_verified = execute_transport_command(
                session=session,
                context=reviewer,
                command_kind="qualification_review",
                operation_id=uuid4(),
                public_payload={
                    "membership_id": str(staff.membership.id),
                    "source_qualification_version_id": str(first_aid_declared.result_id),
                    "decision": "verified",
                    "reason_code": "first_aid_reviewed",
                },
            )
            with pytest.raises(HTTPException) as duplicate_type:
                execute_transport_command(
                    session=session,
                    context=reviewer,
                    command_kind="driver_authorization",
                    operation_id=uuid4(),
                    public_payload={
                        "membership_id": str(staff.membership.id),
                        "capability_version_id": str(capability.result_id),
                        "qualification_version_ids": [
                            str(first_aid_declared.result_id),
                            str(first_aid_verified.result_id),
                        ],
                        "decision": "needs_review",
                        "reason_code": "duplicate_lane_must_fail",
                        "authorization_valid_from": None,
                        "authorization_valid_until": None,
                    },
                )
            assert duplicate_type.value.detail == {
                "code": "authorization_qualification_set_invalid"
            }
            with pytest.raises(HTTPException) as stale_authorization:
                execute_transport_command(
                    session=session,
                    context=reviewer,
                    command_kind="driver_authorization",
                    operation_id=uuid4(),
                    public_payload={
                        "membership_id": str(staff.membership.id),
                        "capability_version_id": str(capability.result_id),
                        "qualification_version_ids": [
                            str(verified.result_id),
                            str(first_aid_declared.result_id),
                        ],
                        "decision": "authorized",
                        "reason_code": "stale_lane_must_fail",
                        "authorization_valid_from": now.isoformat(),
                        "authorization_valid_until": (now + timedelta(days=10)).isoformat(),
                    },
                )
            assert stale_authorization.value.detail == {
                "code": "authorization_qualification_set_invalid"
            }
            authorization = execute_transport_command(
                session=session,
                context=reviewer,
                command_kind="driver_authorization",
                operation_id=uuid4(),
                public_payload={
                    "membership_id": str(staff.membership.id),
                    "capability_version_id": str(capability.result_id),
                    "qualification_version_ids": [
                        str(verified.result_id),
                        str(first_aid_verified.result_id),
                    ],
                    "decision": "authorized",
                    "reason_code": "employment_need_reviewed",
                    "authorization_valid_from": (now + timedelta(seconds=2)).isoformat(),
                    "authorization_valid_until": (now + timedelta(days=10)).isoformat(),
                },
            )
            assert authorization.result_kind == "driver_authorization"
            execute_transport_command(
                session=session,
                context=staff,
                command_kind="qualification_evidence",
                operation_id=uuid4(),
                public_payload={
                    "membership_id": str(staff.membership.id),
                    "qualification_type": "first_aid",
                    "jurisdiction": "CA-AB",
                    "qualification_class": None,
                    "identifier_last4": None,
                    "issue_date": _alberta_today().isoformat(),
                    "expiry_date": (_alberta_today() + timedelta(days=20)).isoformat(),
                    **_evidence_private(
                        now,
                        actor_user_id=staff.user.id,
                        document_id=staff.membership.id,
                        digest="e" * 64,
                    ),
                },
            )
            readiness = execute_transport_command(
                session=session,
                context=reviewer,
                command_kind="readiness_evaluation",
                operation_id=uuid4(),
                public_payload={
                    "membership_id": str(staff.membership.id),
                    "vehicle_id": None,
                },
            )
            assert readiness.result_kind == "driver_readiness"
            readiness_row = session.get(StaffDriverReadinessDecision, readiness.result_id)
            assert readiness_row.decision == "blocked"
            assert "qualification_changed_since_authorization:first_aid" in (
                readiness_row.reason_codes
            )
            assert "qualification_unverified:first_aid" in readiness_row.reason_codes
            notifications = (
                session.query(UserNotification)
                .filter(
                    UserNotification.event_key.like(
                        f"driver-licence-expiry:{staff.membership.id}:%:warning"
                    )
                )
                .all()
            )
            assert {row.user_id for row in notifications} == {
                staff.user.id,
                reviewer.user.id,
            }
            assert {row.title for row in notifications} == {"Driver licence expires soon"}
            assert {row.action_path for row in notifications} == {"/transport-registry"}
            qualification_notifications = (
                session.query(UserNotification)
                .filter(
                    UserNotification.event_key.like(
                        f"driver-qualification-expiry:{staff.membership.id}:%:warning"
                    )
                )
                .all()
            )
            assert {row.user_id for row in qualification_notifications} == {
                staff.user.id,
                reviewer.user.id,
            }
            assert {row.title for row in qualification_notifications} == {
                "Driver qualification expires soon"
            }
            assert {row.action_path for row in qualification_notifications} == {
                "/transport-registry"
            }
