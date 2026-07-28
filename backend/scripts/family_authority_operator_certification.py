"""Certify the signed-in 0029 family-authority operator path on scratch state.

This harness is deliberately incapable of provisioning or migrating PostgreSQL.
It accepts one caller-created, empty, exact-0029D cluster, proves that cluster's
identity in a read-only preflight, and then drives the production FastAPI routes
through an ASGI HTTP client.  All created people, names, email addresses,
passwords, tokens, identifiers, and document bytes are synthetic and are never
written to the redacted receipt.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import ipaddress
import json
import os
import re
import secrets
import stat
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Connection, Engine
from sqlalchemy.pool import NullPool

from app.core.config import BACKEND_ROOT, Settings
from app.main import create_app
from scripts.family_evidence_vault_reconcile import (
    EvidenceVaultReconcileError,
    write_reconcile_report,
)

CERTIFICATION_FORMAT = "caresync-family-authority-operator-certification-v1"
EXACT_REVISION = "0029D_release_checkout_writer"
OPT_IN_ENVIRONMENT = "CARESYNC_RUN_FAMILY_AUTHORITY_OPERATOR_CERTIFICATION"
CONFIRMATION_ENVIRONMENT = "CARESYNC_FAMILY_AUTHORITY_CERTIFY_DISPOSABLE"
OPT_IN_VALUE = "synthetic-only"
PROTECTED_POSTGRES_PORTS = frozenset({5432, 5433, 5434})
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
RUNTIME_ROLE = "caresync_basic_app"
DATABASE_NAME = "caresync"
CANONICAL_CLAMAV_VERSION = re.compile(
    r"ClamAV [0-9]+(?:\.[0-9]+){2}/[0-9]+/"
    r"(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun) "
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) "
    r"(?: [1-9]|[12][0-9]|3[01]) "
    r"(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9] [0-9]{4}"
)


class FamilyAuthorityOperatorCertificationError(RuntimeError):
    """Raised when the bounded operator proof cannot be completed safely."""


@dataclass(frozen=True)
class CertificationTarget:
    host: str
    port: int
    database: str
    runtime_user: str
    runtime_password: str
    attestation_user: str
    attestation_password: str
    expected_data_directory: Path
    expected_system_identifier: str

    @property
    def confirmation(self) -> str:
        directory_digest = hashlib.sha256(
            os.fspath(self.expected_data_directory).encode("utf-8")
        ).hexdigest()
        return (
            f"{self.host}:{self.port}/{self.database}:"
            f"{self.expected_system_identifier}:{directory_digest}"
        )


def _absolute_lexical(path: Path) -> Path:
    return Path(os.path.abspath(os.path.expanduser(os.fspath(path))))


def _validate_target(
    target: CertificationTarget,
    *,
    opt_in: str | None,
    confirmation: str | None,
) -> None:
    if opt_in != OPT_IN_VALUE:
        raise FamilyAuthorityOperatorCertificationError(
            f"Set {OPT_IN_ENVIRONMENT}={OPT_IN_VALUE} to run the synthetic proof"
        )
    if target.host.strip().lower() not in LOOPBACK_HOSTS:
        raise FamilyAuthorityOperatorCertificationError(
            "Operator certification requires a loopback PostgreSQL target"
        )
    if target.port in PROTECTED_POSTGRES_PORTS or not 1 <= target.port <= 65535:
        raise FamilyAuthorityOperatorCertificationError(
            "Operator certification refuses protected or invalid PostgreSQL ports"
        )
    if target.database != DATABASE_NAME or target.runtime_user != RUNTIME_ROLE:
        raise FamilyAuthorityOperatorCertificationError(
            "Operator certification requires the isolated CareSync database and runtime role"
        )
    if not re.fullmatch(r"[1-9][0-9]{10,30}", target.expected_system_identifier):
        raise FamilyAuthorityOperatorCertificationError(
            "Expected PostgreSQL system identifier is invalid"
        )
    if not target.expected_data_directory.is_absolute():
        raise FamilyAuthorityOperatorCertificationError(
            "Expected PostgreSQL data directory must be absolute"
        )
    expected_directory = _absolute_lexical(target.expected_data_directory)
    resolved_directory = expected_directory.resolve(strict=True)
    allowed_roots = {Path("/tmp").resolve(), Path("/private/tmp").resolve()}
    if not any(
        resolved_directory != root and root in resolved_directory.parents for root in allowed_roots
    ):
        raise FamilyAuthorityOperatorCertificationError(
            "Certification PostgreSQL data must be under a private temporary root"
        )
    if not resolved_directory.name.startswith("caresync-authority-cert."):
        raise FamilyAuthorityOperatorCertificationError(
            "Certification PostgreSQL data directory lacks the scratch-only prefix"
        )
    details = resolved_directory.stat()
    expected_owner = os.geteuid() if hasattr(os, "geteuid") else details.st_uid
    if (
        not stat.S_ISDIR(details.st_mode)
        or stat.S_IMODE(details.st_mode) != 0o700
        or details.st_uid != expected_owner
    ):
        raise FamilyAuthorityOperatorCertificationError(
            "Certification PostgreSQL data directory is not private and caller-owned"
        )
    for marker in ("PG_VERSION", "postmaster.pid"):
        marker_path = resolved_directory / marker
        marker_details = marker_path.stat(follow_symlinks=False)
        if not stat.S_ISREG(marker_details.st_mode) or marker_details.st_uid != expected_owner:
            raise FamilyAuthorityOperatorCertificationError(
                "Certification PostgreSQL cluster marker is unsafe"
            )
    if confirmation != target.confirmation:
        raise FamilyAuthorityOperatorCertificationError(
            f"Set {CONFIRMATION_ENVIRONMENT} to the exact scratch-cluster confirmation"
        )


def _database_url(target: CertificationTarget, *, attestation: bool) -> URL:
    return URL.create(
        "postgresql+psycopg",
        username=target.attestation_user if attestation else target.runtime_user,
        password=(target.attestation_password if attestation else target.runtime_password),
        host=target.host,
        port=target.port,
        database=target.database,
    )


def _canonical_clamav_version(value: Any) -> str:
    if not isinstance(value, str) or CANONICAL_CLAMAV_VERSION.fullmatch(value) is None:
        raise FamilyAuthorityOperatorCertificationError(
            "Scanner returned a non-canonical or unsafe ClamAV version"
        )
    return value


def _target_identity(connection: Connection) -> tuple[Any, ...]:
    return connection.execute(
        text(
            "SELECT current_user, current_database(), "
            "COALESCE(inet_server_addr()::text,''), inet_server_port(), "
            "current_setting('data_directory'), pg_backend_pid()"
        )
    ).one()


def _validate_observed_target(
    target: CertificationTarget,
    *,
    identity: tuple[Any, ...],
    system_identifier: str,
    revisions: list[str],
) -> None:
    if identity[0] != target.attestation_user or identity[1] != target.database:
        raise FamilyAuthorityOperatorCertificationError(
            "Scratch PostgreSQL identity differs from the caller attestation"
        )
    try:
        server_address = ipaddress.ip_interface(str(identity[2]).split("%", maxsplit=1)[0]).ip
    except ValueError as error:
        raise FamilyAuthorityOperatorCertificationError(
            "Scratch PostgreSQL did not report a valid server address"
        ) from error
    if not server_address.is_loopback:
        raise FamilyAuthorityOperatorCertificationError(
            "Scratch PostgreSQL server address is not loopback"
        )
    if int(identity[3]) != target.port:
        raise FamilyAuthorityOperatorCertificationError(
            "Scratch PostgreSQL server port differs from the caller attestation"
        )
    if _absolute_lexical(Path(identity[4])).resolve(strict=True) != (
        _absolute_lexical(target.expected_data_directory).resolve(strict=True)
    ):
        raise FamilyAuthorityOperatorCertificationError(
            "PostgreSQL reports a different data directory"
        )
    if system_identifier != target.expected_system_identifier:
        raise FamilyAuthorityOperatorCertificationError(
            "PostgreSQL reports a different system identifier"
        )
    if revisions != [EXACT_REVISION]:
        raise FamilyAuthorityOperatorCertificationError(
            "Operator certification requires exact pre-migrated 0029D"
        )


def _preflight_empty_exact_target(
    target: CertificationTarget,
    connection: Connection,
) -> dict[str, Any]:
    """Attest exact scratch identity and emptiness without writing a row."""

    try:
        identity = _target_identity(connection)
        system_identifier = str(
            connection.execute(
                text("SELECT system_identifier FROM pg_control_system()")
            ).scalar_one()
        )
        revisions = list(
            connection.execute(
                text("SELECT version_num FROM alembic_version ORDER BY version_num")
            ).scalars()
        )
        counts = {
            table_name: int(
                connection.execute(text(f'SELECT count(*) FROM "{table_name}"')).scalar_one()
            )
            for table_name in (
                "organizations",
                "users",
                "families",
                "children",
                "family_authority_evidence_objects",
                "family_authority_evidence",
                "child_release_authorizations",
            )
        }
        other_sessions = int(
            connection.execute(
                text(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE datname=current_database() AND pid<>pg_backend_pid()"
                )
            ).scalar_one()
        )
    except Exception as error:
        raise FamilyAuthorityOperatorCertificationError(
            "Scratch PostgreSQL preflight could not be completed"
        ) from error

    _validate_observed_target(
        target,
        identity=identity,
        system_identifier=system_identifier,
        revisions=revisions,
    )
    if any(counts.values()):
        raise FamilyAuthorityOperatorCertificationError(
            "Operator certification requires an empty scratch application database"
        )
    if other_sessions:
        raise FamilyAuthorityOperatorCertificationError(
            "Scratch PostgreSQL has another client session"
        )
    return {
        "revision": EXACT_REVISION,
        "systemIdentifierSha256": hashlib.sha256(system_identifier.encode("ascii")).hexdigest(),
        "baselineTablesEmpty": True,
        "otherClientSessions": 0,
        "sentinelBackendPid": int(identity[5]),
    }


def _postflight_exact_target(
    target: CertificationTarget,
    engine: Engine,
    *,
    sentinel_backend_pid: int,
) -> dict[str, Any]:
    expected_counts = {
        "organizations": 1,
        "users": 2,
        "organization_memberships": 2,
        "staff_invitations": 1,
        "families": 1,
        "children": 1,
        "family_authority_people": 2,
        "family_authority_person_versions": 2,
        "family_authority_evidence_objects": 1,
        "family_authority_evidence_object_assessments": 2,
        "family_authority_evidence": 1,
        "family_authority_evidence_assessments": 1,
        "child_authority_heads": 1,
        "child_release_authorizations": 1,
        "childcare_command_receipts": 9,
        "audit_events": 12,
        "realtime_events": 6,
        "realtime_tickets": 1,
    }
    try:
        with engine.connect() as connection, connection.begin():
            connection.exec_driver_sql("SET TRANSACTION READ ONLY")
            identity = _target_identity(connection)
            system_identifier = str(
                connection.execute(
                    text("SELECT system_identifier FROM pg_control_system()")
                ).scalar_one()
            )
            revisions = list(
                connection.execute(
                    text("SELECT version_num FROM alembic_version ORDER BY version_num")
                ).scalars()
            )
            counts = {
                table_name: int(
                    connection.execute(text(f'SELECT count(*) FROM "{table_name}"')).scalar_one()
                )
                for table_name in expected_counts
            }
            session_state = connection.execute(
                text(
                    "SELECT "
                    "count(*) FILTER (WHERE pid=:sentinel_backend_pid "
                    "AND usename=:attestation_user),"
                    "count(*) FILTER (WHERE pid<>pg_backend_pid() "
                    "AND pid<>:sentinel_backend_pid) "
                    "FROM pg_stat_activity WHERE datname=current_database()"
                ),
                {
                    "sentinel_backend_pid": sentinel_backend_pid,
                    "attestation_user": target.attestation_user,
                },
            ).one()
    except Exception as error:
        raise FamilyAuthorityOperatorCertificationError(
            "Scratch PostgreSQL postflight could not be completed"
        ) from error

    _validate_observed_target(
        target,
        identity=identity,
        system_identifier=system_identifier,
        revisions=revisions,
    )
    if counts != expected_counts:
        raise FamilyAuthorityOperatorCertificationError(
            "Postflight synthetic row counts differ from the certified flow"
        )
    if int(session_state[0]) != 1 or int(session_state[1]) != 0:
        raise FamilyAuthorityOperatorCertificationError(
            "Postflight found a missing sentinel or an unexpected client session"
        )
    return {
        "postflightSameSystemIdentifier": True,
        "postflightExactRevision": True,
        "postflightExpectedSyntheticRows": True,
        "postflightUnexpectedClientSessions": 0,
    }


def _expect_json(response: Any, status_code: int, label: str) -> dict[str, Any]:
    if response.status_code != status_code:
        raise FamilyAuthorityOperatorCertificationError(
            f"{label} returned HTTP {response.status_code}"
        )
    try:
        value = response.json()
    except ValueError as error:
        raise FamilyAuthorityOperatorCertificationError(f"{label} did not return JSON") from error
    if not isinstance(value, dict):
        raise FamilyAuthorityOperatorCertificationError(
            f"{label} returned an invalid response shape"
        )
    return value


def _bearer(auth: dict[str, Any]) -> dict[str, str]:
    token = auth.get("access_token")
    if not isinstance(token, str) or not token:
        raise FamilyAuthorityOperatorCertificationError(
            "Authentication response omitted its bearer token"
        )
    return {"Authorization": f"Bearer {token}"}


def _png_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (24, 24), (72, 164, 190)).save(output, format="PNG")
    return output.getvalue()


def _read_only_snapshot(
    engine: Engine,
    statement: str,
    parameters: dict[str, Any],
) -> tuple[Any, ...]:
    try:
        with engine.connect() as connection, connection.begin():
            connection.exec_driver_sql("SET TRANSACTION READ ONLY")
            return tuple(connection.execute(text(statement), parameters).one())
    except Exception as error:
        raise FamilyAuthorityOperatorCertificationError(
            "Scratch PostgreSQL mutation attestation could not be completed"
        ) from error


def _operation_surface_snapshot(
    engine: Engine,
    organization_id: str,
    operation_id: str,
) -> dict[str, int]:
    values = _read_only_snapshot(
        engine,
        "SELECT "
        "(SELECT count(*) FROM childcare_command_receipts "
        " WHERE organization_id=CAST(:organization_id AS uuid)),"
        "(SELECT count(*) FROM childcare_command_receipts "
        " WHERE organization_id=CAST(:organization_id AS uuid) "
        "   AND client_operation_id=CAST(:operation_id AS uuid)),"
        "(SELECT count(*) FROM audit_events "
        " WHERE organization_id=CAST(:organization_id AS uuid)),"
        "(SELECT count(*) FROM realtime_events "
        " WHERE organization_id=CAST(:organization_id AS uuid)),"
        "(SELECT count(*) FROM family_authority_evidence_assessments "
        " WHERE organization_id=CAST(:organization_id AS uuid))",
        {"organization_id": organization_id, "operation_id": operation_id},
    )
    return dict(
        zip(
            (
                "receiptCount",
                "operationReceiptCount",
                "auditCount",
                "realtimeCount",
                "evidenceAssessmentCount",
            ),
            (int(value) for value in values),
            strict=True,
        )
    )


def _upload_scan_replay_counts(
    engine: Engine,
    organization_id: str,
    upload_operation_id: str,
    scan_operation_id: str,
) -> tuple[int, int, int, int]:
    return tuple(
        int(value)
        for value in _read_only_snapshot(
            engine,
            "SELECT "
            "(SELECT count(*) FROM family_authority_evidence_objects "
            " WHERE organization_id=CAST(:organization_id AS uuid) "
            "   AND uploaded_operation_id=CAST(:upload_operation_id AS uuid)),"
            "(SELECT count(*) FROM family_authority_evidence_object_assessments "
            " WHERE organization_id=CAST(:organization_id AS uuid) "
            "   AND operation_id=CAST(:scan_operation_id AS uuid)),"
            "(SELECT count(*) FROM childcare_command_receipts "
            " WHERE organization_id=CAST(:organization_id AS uuid) "
            "   AND client_operation_id=CAST(:upload_operation_id AS uuid)),"
            "(SELECT count(*) FROM childcare_command_receipts "
            " WHERE organization_id=CAST(:organization_id AS uuid) "
            "   AND client_operation_id=CAST(:scan_operation_id AS uuid))",
            {
                "organization_id": organization_id,
                "upload_operation_id": upload_operation_id,
                "scan_operation_id": scan_operation_id,
            },
        )
    )


def _activation_snapshot(
    engine: Engine,
    organization_id: str,
    child_id: str,
    operation_id: str,
) -> dict[str, Any]:
    counts = _read_only_snapshot(
        engine,
        "SELECT "
        "(SELECT count(*) FROM child_release_authorizations "
        " WHERE organization_id=CAST(:organization_id AS uuid) "
        "   AND child_id=CAST(:child_id AS uuid) "
        "   AND created_operation_id=CAST(:operation_id AS uuid)),"
        "(SELECT count(*) FROM childcare_command_receipts "
        " WHERE organization_id=CAST(:organization_id AS uuid) "
        "   AND client_operation_id=CAST(:operation_id AS uuid)),"
        "(SELECT count(*) FROM child_release_authorizations "
        " WHERE organization_id=CAST(:organization_id AS uuid)),"
        "(SELECT count(*) FROM childcare_command_receipts "
        " WHERE organization_id=CAST(:organization_id AS uuid)),"
        "(SELECT count(*) FROM audit_events "
        " WHERE organization_id=CAST(:organization_id AS uuid)),"
        "(SELECT count(*) FROM realtime_events "
        " WHERE organization_id=CAST(:organization_id AS uuid)),"
        "COALESCE((SELECT revision FROM child_authority_heads "
        " WHERE organization_id=CAST(:organization_id AS uuid) "
        "   AND child_id=CAST(:child_id AS uuid)),0)",
        {
            "organization_id": organization_id,
            "child_id": child_id,
            "operation_id": operation_id,
        },
    )
    realtime_rows = _read_realtime_invalidation(
        engine,
        organization_id=organization_id,
    )
    return {
        "operationAuthorizationCount": int(counts[0]),
        "operationReceiptCount": int(counts[1]),
        "authorizationCount": int(counts[2]),
        "receiptCount": int(counts[3]),
        "auditCount": int(counts[4]),
        "realtimeCount": int(counts[5]),
        "authorityRevision": int(counts[6]),
        "invalidationRows": realtime_rows,
    }


def _read_realtime_invalidation(
    engine: Engine,
    *,
    organization_id: str,
) -> list[dict[str, Any]]:
    try:
        with engine.connect() as connection, connection.begin():
            connection.exec_driver_sql("SET TRANSACTION READ ONLY")
            rows = connection.execute(
                text(
                    "SELECT event_type,entity_type,entity_id,payload "
                    "FROM realtime_events "
                    "WHERE organization_id=CAST(:organization_id AS uuid) "
                    "AND event_type='family_authority.release_context_invalidated' "
                    "ORDER BY sequence_id"
                ),
                {"organization_id": organization_id},
            ).all()
    except Exception as error:
        raise FamilyAuthorityOperatorCertificationError(
            "Scratch PostgreSQL realtime attestation could not be completed"
        ) from error
    return [
        {
            "eventType": row.event_type,
            "entityType": row.entity_type,
            "entityId": row.entity_id,
            "payload": row.payload,
        }
        for row in rows
    ]


def _latest_realtime_cursor(engine: Engine, organization_id: str) -> int:
    return int(
        _read_only_snapshot(
            engine,
            "SELECT COALESCE(max(sequence_id),0) FROM realtime_events "
            "WHERE organization_id=CAST(:organization_id AS uuid)",
            {"organization_id": organization_id},
        )[0]
    )


def _workspace_evidence(
    client: TestClient,
    headers: dict[str, str],
    family_id: str,
    evidence_id: str,
) -> dict[str, Any]:
    workspace = _expect_json(
        client.get(f"/api/v1/families/{family_id}/authority", headers=headers),
        200,
        "authority workspace",
    )
    evidence = workspace.get("evidence")
    if not isinstance(evidence, list):
        raise FamilyAuthorityOperatorCertificationError("Authority workspace omitted evidence")
    matches = [row for row in evidence if isinstance(row, dict) and row.get("id") == evidence_id]
    if len(matches) != 1:
        raise FamilyAuthorityOperatorCertificationError(
            "Authority workspace did not return the exact evidence row"
        )
    return matches[0]


def _authority_person(
    client: TestClient,
    headers: dict[str, str],
    family_id: str,
    label: str,
) -> dict[str, Any]:
    response = _expect_json(
        client.post(
            f"/api/v1/families/{family_id}/authority/people",
            headers=headers,
            json={
                "client_operation_id": str(uuid4()),
                "source": {"kind": "manual"},
                "facts": {
                    "first_name": label,
                    "last_name": "Synthetic",
                    "relationship_kind": "family_friend",
                    "email": f"{label.lower()}-{uuid4().hex}@example.invalid",
                    "primary_phone": "+1-780-555-0100",
                },
            },
        ),
        201,
        f"{label} authority-person creation",
    )
    resource = response.get("resource")
    if not isinstance(resource, dict) or not isinstance(resource.get("current_version"), dict):
        raise FamilyAuthorityOperatorCertificationError(
            "Authority-person creation returned an invalid resource"
        )
    return resource


def _run_public_http_flow(
    client: TestClient,
    *,
    attestation_engine: Engine,
    vault_root: Path,
) -> dict[str, Any]:
    owner_password = secrets.token_urlsafe(24)
    admin_password = secrets.token_urlsafe(24)
    owner_email = f"owner-{uuid4().hex}@example.invalid"
    admin_email = f"admin-{uuid4().hex}@example.invalid"

    owner_auth = _expect_json(
        client.post(
            "/api/v1/auth/register",
            json={
                "email": owner_email,
                "password": owner_password,
                "first_name": "Synthetic",
                "last_name": "Owner",
                "organization_name": "Synthetic Operator Certification",
            },
        ),
        201,
        "owner registration",
    )
    owner_headers = _bearer(owner_auth)
    owner_user = owner_auth.get("user")
    if not isinstance(owner_user, dict):
        raise FamilyAuthorityOperatorCertificationError(
            "Owner registration omitted the authenticated user"
        )
    organization_id = owner_user.get("organization_id")
    if not isinstance(organization_id, str) or not organization_id:
        raise FamilyAuthorityOperatorCertificationError(
            "Owner registration omitted its synthetic organization identity"
        )

    staff_workspace = _expect_json(
        client.get("/api/v1/staff/workspace", headers=owner_headers),
        200,
        "staff workspace",
    )
    roles = staff_workspace.get("roles")
    administrator_roles = (
        [role for role in roles if isinstance(role, dict) and role.get("key") == "administrator"]
        if isinstance(roles, list)
        else []
    )
    if len(administrator_roles) != 1:
        raise FamilyAuthorityOperatorCertificationError(
            "Staff workspace did not expose exactly one administrator role"
        )
    invitation = _expect_json(
        client.post(
            "/api/v1/staff/invitations",
            headers=owner_headers,
            json={
                "email": admin_email,
                "first_name": "Synthetic",
                "last_name": "Checker",
                "role_id": administrator_roles[0]["id"],
                "assigned_facility_ids": [],
                "assigned_room_ids": [],
            },
        ),
        201,
        "administrator invitation",
    )
    activation_url = invitation.get("activation_url")
    if not isinstance(activation_url, str):
        raise FamilyAuthorityOperatorCertificationError(
            "Administrator invitation omitted its one-time activation route"
        )
    parsed = urlparse(activation_url)
    tokens = parse_qs(parsed.fragment).get("token", [])
    if parsed.path != "/activate-staff" or len(tokens) != 1 or not tokens[0]:
        raise FamilyAuthorityOperatorCertificationError(
            "Administrator invitation returned an unsafe activation route"
        )
    token = tokens[0]
    preview = _expect_json(
        client.post("/api/v1/auth/staff-activation", json={"token": token}),
        200,
        "administrator activation preview",
    )
    if preview.get("email") != admin_email or preview.get("role_name") != "Administrator":
        raise FamilyAuthorityOperatorCertificationError(
            "Administrator activation preview changed the invited identity or role"
        )
    admin_auth = _expect_json(
        client.post(
            "/api/v1/auth/staff-activation/accept",
            json={"token": token, "password": admin_password},
        ),
        200,
        "administrator activation",
    )
    admin_headers = _bearer(admin_auth)
    admin_user = admin_auth.get("user")
    if (
        not isinstance(admin_user, dict)
        or admin_user.get("role", {}).get("key") != "administrator"
        or admin_user.get("id") == owner_user.get("id")
    ):
        raise FamilyAuthorityOperatorCertificationError(
            "Administrator activation did not create a distinct administrator actor"
        )

    family = _expect_json(
        client.post(
            "/api/v1/families",
            headers=owner_headers,
            json={
                "client_operation_id": str(uuid4()),
                "name": "Synthetic Certification Family",
            },
        ),
        201,
        "family creation",
    )
    child = _expect_json(
        client.post(
            "/api/v1/children",
            headers=owner_headers,
            json={
                "client_operation_id": str(uuid4()),
                "family_id": family["id"],
                "first_name": "Synthetic",
                "last_name": "Child",
                "date_of_birth": "2024-01-01",
            },
        ),
        201,
        "child creation",
    )
    grantor = _authority_person(client, owner_headers, family["id"], "Custodian")
    recipient = _authority_person(client, owner_headers, family["id"], "Recipient")

    document = _png_bytes()
    upload_operation_id = str(uuid4())
    upload_path = f"/api/v1/families/{family['id']}/authority/evidence-objects"
    upload_data = {
        "client_operation_id": upload_operation_id,
        "evidence_kind": "custody_document",
    }
    uploaded = _expect_json(
        client.post(
            upload_path,
            headers=owner_headers,
            data=upload_data,
            files={"file": ("synthetic-custody.png", document, "image/png")},
        ),
        201,
        "multipart evidence upload",
    )
    evidence_object = uploaded.get("resource")
    if (
        not isinstance(evidence_object, dict)
        or evidence_object.get("lifecycle_status") != "quarantined"
        or evidence_object.get("content_sha256") != hashlib.sha256(document).hexdigest()
    ):
        raise FamilyAuthorityOperatorCertificationError(
            "Multipart evidence upload did not preserve measured quarantined identity"
        )
    upload_replay = _expect_json(
        client.post(
            upload_path,
            headers=owner_headers,
            data=upload_data,
            files={"file": ("synthetic-custody.png", document, "image/png")},
        ),
        201,
        "multipart evidence exact replay",
    )
    upload_replay_resource = upload_replay.get("resource")
    if (
        upload_replay.get("replayed") is not True
        or not isinstance(upload_replay_resource, dict)
        or upload_replay_resource.get("id") != evidence_object.get("id")
        or upload_replay.get("receipt") != uploaded.get("receipt")
        or len(list(vault_root.rglob("v1.png"))) != 1
    ):
        raise FamilyAuthorityOperatorCertificationError(
            "Multipart upload exact replay duplicated or changed private evidence"
        )

    scan_operation_id = str(uuid4())
    scan_path = (
        f"/api/v1/families/{family['id']}/authority/evidence-objects/{evidence_object['id']}/scan"
    )
    scan_payload = {
        "client_operation_id": scan_operation_id,
        "expected_version": 1,
    }
    scanned = _expect_json(
        client.post(
            scan_path,
            headers=owner_headers,
            json=scan_payload,
        ),
        200,
        "production evidence scan",
    )
    scanned_object = scanned.get("resource")
    scan_assessment = (
        scanned_object.get("current_assessment") if isinstance(scanned_object, dict) else None
    )
    if (
        not isinstance(scan_assessment, dict)
        or scanned_object.get("lifecycle_status") != "clean"
        or scan_assessment.get("scanner_engine") != "clamscan"
        or not isinstance(scan_assessment.get("scanner_version"), str)
    ):
        raise FamilyAuthorityOperatorCertificationError(
            "Production scanner did not return a clean clamscan assessment"
        )
    scanner_version = _canonical_clamav_version(scan_assessment["scanner_version"])
    scan_replay = _expect_json(
        client.post(
            scan_path,
            headers=owner_headers,
            json=scan_payload,
        ),
        200,
        "production evidence scan exact replay",
    )
    scan_replay_resource = scan_replay.get("resource")
    replay_assessment = (
        scan_replay_resource.get("current_assessment")
        if isinstance(scan_replay_resource, dict)
        else None
    )
    if (
        scan_replay.get("replayed") is not True
        or not isinstance(replay_assessment, dict)
        or scan_replay_resource.get("id") != scanned_object.get("id")
        or scan_replay_resource.get("lifecycle_status") != "clean"
        or replay_assessment.get("id") != scan_assessment.get("id")
        or scan_replay.get("receipt") != scanned.get("receipt")
    ):
        raise FamilyAuthorityOperatorCertificationError(
            "Production scan exact replay duplicated or changed its decision"
        )
    if _upload_scan_replay_counts(
        attestation_engine,
        organization_id,
        upload_operation_id,
        scan_operation_id,
    ) != (1, 1, 1, 1):
        raise FamilyAuthorityOperatorCertificationError(
            "Upload or scan exact replay created duplicate database rows"
        )

    downloaded = client.get(
        f"/api/v1/families/{family['id']}/authority/evidence-objects/"
        f"{evidence_object['id']}/download",
        headers=owner_headers,
    )
    if (
        downloaded.status_code != 200
        or downloaded.content != document
        or downloaded.headers.get("content-type") != "image/png"
        or downloaded.headers.get("content-length") != str(len(document))
        or downloaded.headers.get("cache-control") != "private, no-store"
        or downloaded.headers.get("pragma") != "no-cache"
        or downloaded.headers.get("x-content-type-options") != "nosniff"
        or re.fullmatch(
            r'attachment; filename="evidence-[0-9a-f-]{36}\.png"',
            downloaded.headers.get("content-disposition", ""),
        )
        is None
        or "synthetic-custody" in downloaded.headers.get("content-disposition", "")
    ):
        raise FamilyAuthorityOperatorCertificationError(
            "Clean evidence download changed bytes or omitted private response headers"
        )

    recorded = _expect_json(
        client.post(
            f"/api/v1/families/{family['id']}/authority/evidence",
            headers=owner_headers,
            json={
                "client_operation_id": str(uuid4()),
                "evidence_kind": "custody_document",
                "source_label": "Synthetic custody evidence",
                "captured_at": datetime.now(UTC).isoformat(),
                "evidence_object_id": evidence_object["id"],
            },
        ),
        201,
        "evidence recording",
    )
    evidence = recorded.get("resource")
    if not isinstance(evidence, dict) or evidence.get("lifecycle_status") != "unreviewed":
        raise FamilyAuthorityOperatorCertificationError(
            "Recorded evidence did not begin unreviewed"
        )

    maker_review_operation_id = str(uuid4())
    before_maker_rejection = _operation_surface_snapshot(
        attestation_engine,
        organization_id,
        maker_review_operation_id,
    )
    maker_review = client.post(
        f"/api/v1/families/{family['id']}/authority/evidence/{evidence['id']}/review",
        headers=owner_headers,
        json={
            "client_operation_id": maker_review_operation_id,
            "expected_version": 1,
            "assessed_epistemic_status": "document_observed",
        },
    )
    maker_error = _expect_json(maker_review, 409, "maker review rejection")
    if maker_error.get("detail", {}).get("code") != "maker_checker_required":
        raise FamilyAuthorityOperatorCertificationError(
            "Maker review failed with the wrong bounded reason"
        )
    after_maker_rejection = _operation_surface_snapshot(
        attestation_engine,
        organization_id,
        maker_review_operation_id,
    )
    if (
        before_maker_rejection != after_maker_rejection
        or after_maker_rejection["operationReceiptCount"] != 0
    ):
        raise FamilyAuthorityOperatorCertificationError(
            "Rejected maker review wrote a receipt, audit, realtime, or assessment row"
        )
    unchanged = _workspace_evidence(client, owner_headers, family["id"], evidence["id"])
    if (
        unchanged.get("version") != 1
        or unchanged.get("lifecycle_status") != "unreviewed"
        or unchanged.get("current_assessment") is not None
    ):
        raise FamilyAuthorityOperatorCertificationError(
            "Rejected maker review changed the evidence row"
        )

    reviewed = _expect_json(
        client.post(
            f"/api/v1/families/{family['id']}/authority/evidence/{evidence['id']}/review",
            headers=admin_headers,
            json={
                "client_operation_id": str(uuid4()),
                "expected_version": 1,
                "assessed_epistemic_status": "document_observed",
            },
        ),
        200,
        "independent checker review",
    )
    reviewed_evidence = reviewed.get("resource")
    assessment = (
        reviewed_evidence.get("current_assessment") if isinstance(reviewed_evidence, dict) else None
    )
    if (
        not isinstance(assessment, dict)
        or reviewed_evidence.get("lifecycle_status") != "reviewed"
        or reviewed_evidence.get("valid_now") is not True
        or assessment.get("actor_user_id") != admin_user.get("id")
    ):
        raise FamilyAuthorityOperatorCertificationError(
            "Independent checker review did not become the current assessment"
        )

    effective_from = datetime.now(UTC) + timedelta(minutes=5)
    activation_operation_id = str(uuid4())
    activation_path = f"/api/v1/children/{child['id']}/release-authorizations"
    activation_payload = {
        "client_operation_id": activation_operation_id,
        "expected_authority_revision": 0,
        "recipient_person_id": recipient["id"],
        "verification_policy_code": "government_photo_id",
        "grantor": {
            "person_id": grantor["id"],
            "person_version_id": grantor["current_version"]["id"],
            "authority_basis": "reviewed_custody_evidence",
            "basis_evidence_id": evidence["id"],
            "basis_evidence_assessment_id": assessment["id"],
        },
        "effective_from": effective_from.isoformat(),
        "effective_until": (effective_from + timedelta(days=30)).isoformat(),
    }
    realtime_cursor_before_activation = _latest_realtime_cursor(
        attestation_engine,
        organization_id,
    )
    activated = _expect_json(
        client.post(
            activation_path,
            headers=owner_headers,
            json=activation_payload,
        ),
        201,
        "reviewed authority activation",
    )
    authorization = activated.get("resource")
    if (
        not isinstance(authorization, dict)
        or authorization.get("authority_revision") != 1
        or authorization.get("grantor", {}).get("authority_basis") != "reviewed_custody_evidence"
    ):
        raise FamilyAuthorityOperatorCertificationError(
            "Reviewed evidence did not activate the expected authority lane"
        )
    activation_state = _activation_snapshot(
        attestation_engine,
        organization_id,
        child["id"],
        activation_operation_id,
    )
    expected_invalidation = [
        {
            "eventType": "family_authority.release_context_invalidated",
            "entityType": "child_authority_head",
            "entityId": None,
            "payload": {"source": "authority_head", "scope": "release_context"},
        }
    ]
    if (
        activation_state["operationAuthorizationCount"] != 1
        or activation_state["operationReceiptCount"] != 1
        or activation_state["authorityRevision"] != 1
        or activation_state["invalidationRows"] != expected_invalidation
    ):
        raise FamilyAuthorityOperatorCertificationError(
            "Authority activation did not commit one row and one PII-free invalidation"
        )
    activation_replay = _expect_json(
        client.post(
            activation_path,
            headers=owner_headers,
            json=activation_payload,
        ),
        201,
        "reviewed authority activation exact replay",
    )
    activation_replay_resource = activation_replay.get("resource")
    if (
        activation_replay.get("replayed") is not True
        or not isinstance(activation_replay_resource, dict)
        or activation_replay_resource.get("id") != authorization.get("id")
        or activation_replay_resource.get("authority_revision") != 1
        or activation_replay.get("receipt") != activated.get("receipt")
        or _activation_snapshot(
            attestation_engine,
            organization_id,
            child["id"],
            activation_operation_id,
        )
        != activation_state
    ):
        raise FamilyAuthorityOperatorCertificationError(
            "Authority activation exact replay created a duplicate or changed state"
        )
    issued_ticket = _expect_json(
        client.post("/api/v1/realtime/tickets", headers=owner_headers),
        201,
        "tenant realtime ticket",
    )
    realtime_ticket = issued_ticket.get("ticket")
    if (
        not isinstance(realtime_ticket, str)
        or not realtime_ticket
        or issued_ticket.get("websocket_path") != "/api/v1/realtime/ws"
    ):
        raise FamilyAuthorityOperatorCertificationError(
            "Tenant realtime ticket returned an invalid bounded route"
        )
    with client.websocket_connect(
        f"/api/v1/realtime/ws?ticket={realtime_ticket}&after={realtime_cursor_before_activation}"
    ) as websocket:
        ready_frame = websocket.receive_json()
        event_frame = websocket.receive_json()
    event_value = event_frame.get("event") if isinstance(event_frame, dict) else None
    if (
        not isinstance(ready_frame, dict)
        or ready_frame.get("type") != "ready"
        or ready_frame.get("organization_id") != organization_id
        or ready_frame.get("cursor") != realtime_cursor_before_activation
        or not isinstance(event_value, dict)
        or event_frame.get("type") != "event"
        or event_value.get("type") != "family_authority.release_context_invalidated"
        or event_value.get("entity_type") != "child_authority_head"
        or event_value.get("entity_id") is not None
        or event_value.get("payload") != {"source": "authority_head", "scope": "release_context"}
    ):
        raise FamilyAuthorityOperatorCertificationError(
            "Tenant WebSocket did not replay the exact PII-free authority invalidation"
        )
    summary = _expect_json(
        client.get(
            f"/api/v1/children/{child['id']}/authority-summary",
            headers=owner_headers,
        ),
        200,
        "child authority summary",
    )
    if summary.get("authority_revision") != 1 or summary.get("reviewed") is not True:
        raise FamilyAuthorityOperatorCertificationError(
            "Activated authority did not reach the administrative summary"
        )

    return {
        "scannerEngine": scan_assessment["scanner_engine"],
        "scannerVersion": scanner_version,
        "authorityRevision": authorization["authority_revision"],
        "organizationId": organization_id,
    }


def _validate_completed_receipt_payload(payload: dict[str, Any]) -> None:
    expected_top_level = {
        "format",
        "generatedAt",
        "result",
        "scope",
        "target",
        "scanner",
        "cases",
        "redaction",
    }
    if set(payload) != expected_top_level:
        raise FamilyAuthorityOperatorCertificationError(
            "Certification payload is incomplete or contains unapproved fields"
        )
    if payload.get("format") != CERTIFICATION_FORMAT or payload.get("result") != "passed":
        raise FamilyAuthorityOperatorCertificationError(
            "Only a completed operator certification can produce a receipt"
        )
    generated_at = payload.get("generatedAt")
    try:
        parsed = datetime.fromisoformat(str(generated_at).replace("Z", "+00:00"))
    except ValueError as error:
        raise FamilyAuthorityOperatorCertificationError(
            "Certification generation time is invalid"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise FamilyAuthorityOperatorCertificationError(
            "Certification generation time must include a timezone"
        )
    expected_scope = {
        "syntheticOnly": True,
        "publicHttpRoutes": True,
        "inProcessAsgi": True,
        "attestationSentinelHeld": True,
        "callerProvisionedDatabase": True,
        "databaseProvisionedByHarness": False,
        "alembicInvoked": False,
        "databaseDroppedOrTruncated": False,
        "protectedPortsContacted": False,
        "retainedDataAccessed": False,
        "releaseAuthority": False,
        "cutoverAuthority": False,
    }
    expected_cases = {
        "ownerRegistration": True,
        "administratorInvitationActivation": True,
        "productionMultipartUpload": True,
        "uploadExactReplayNoDuplicateObject": True,
        "productionClamscanClean": True,
        "scanExactReplayNoDuplicateAssessment": True,
        "cleanDocumentDownload": True,
        "evidenceRecorded": True,
        "makerReviewRejected409": True,
        "makerReviewNoWriteAttested": True,
        "independentCheckerReview": True,
        "reviewedAuthorityActivation": True,
        "activationExactReplayNoDuplicateRows": True,
        "piiFreeRealtimeInvalidation": True,
        "publicRealtimeWebSocketReplay": True,
        "administrativeSummaryObserved": True,
    }
    expected_redaction = {
        "credentialsRecorded": False,
        "tokensRecorded": False,
        "emailsRecorded": False,
        "personNamesRecorded": False,
        "recordIdentifiersRecorded": False,
        "documentBytesRecorded": False,
        "vaultPathsRecorded": False,
        "databaseDataDirectoryRecorded": False,
        "scannerAbsolutePathRecorded": False,
    }
    if payload.get("scope") != expected_scope:
        raise FamilyAuthorityOperatorCertificationError("Certification scope is incomplete")
    if payload.get("cases") != expected_cases:
        raise FamilyAuthorityOperatorCertificationError("Certification cases are incomplete")
    if payload.get("redaction") != expected_redaction:
        raise FamilyAuthorityOperatorCertificationError(
            "Certification redaction contract is incomplete"
        )
    target = payload.get("target")
    if not isinstance(target, dict) or set(target) != {
        "hostClass",
        "databaseName",
        "runtimeRole",
        "revision",
        "systemIdentifierSha256",
        "baselineTablesEmpty",
        "otherClientSessions",
        "postflightSameSystemIdentifier",
        "postflightExactRevision",
        "postflightExpectedSyntheticRows",
        "postflightUnexpectedClientSessions",
    }:
        raise FamilyAuthorityOperatorCertificationError(
            "Certification target attestation is invalid"
        )
    if (
        target.get("hostClass") != "loopback"
        or target.get("databaseName") != DATABASE_NAME
        or target.get("runtimeRole") != RUNTIME_ROLE
        or target.get("revision") != EXACT_REVISION
        or not re.fullmatch(r"[0-9a-f]{64}", str(target.get("systemIdentifierSha256")))
        or target.get("baselineTablesEmpty") is not True
        or target.get("otherClientSessions") != 0
        or target.get("postflightSameSystemIdentifier") is not True
        or target.get("postflightExactRevision") is not True
        or target.get("postflightExpectedSyntheticRows") is not True
        or target.get("postflightUnexpectedClientSessions") != 0
    ):
        raise FamilyAuthorityOperatorCertificationError(
            "Certification target attestation did not pass"
        )
    scanner = payload.get("scanner")
    if not isinstance(scanner, dict) or set(scanner) != {
        "engine",
        "version",
        "executableName",
        "definitionFreshnessEnforced",
    }:
        raise FamilyAuthorityOperatorCertificationError(
            "Certification scanner attestation is invalid"
        )
    if (
        scanner.get("engine") != "clamscan"
        or scanner.get("executableName") != "clamscan"
        or scanner.get("definitionFreshnessEnforced") is not True
    ):
        raise FamilyAuthorityOperatorCertificationError(
            "Certification scanner attestation did not pass"
        )
    _canonical_clamav_version(scanner.get("version"))


def certify_family_authority_operator_flow(
    target: CertificationTarget,
    scanner_path: Path,
    *,
    opt_in: str | None,
    confirmation: str | None,
) -> dict[str, Any]:
    _validate_target(target, opt_in=opt_in, confirmation=confirmation)
    scanner = _absolute_lexical(scanner_path)
    if not scanner_path.is_absolute() or scanner.name != "clamscan":
        raise FamilyAuthorityOperatorCertificationError(
            "Operator certification requires an absolute clamscan executable"
        )
    if not scanner.is_file() or not os.access(scanner, os.X_OK):
        raise FamilyAuthorityOperatorCertificationError(
            "Configured clamscan executable is unavailable"
        )
    attestation_engine = create_engine(
        _database_url(target, attestation=True),
        poolclass=NullPool,
    )
    try:
        with (
            attestation_engine.connect().execution_options(
                isolation_level="SERIALIZABLE"
            ) as sentinel,
            sentinel.begin(),
        ):
            sentinel.exec_driver_sql("SET TRANSACTION READ ONLY, DEFERRABLE")
            preflight = _preflight_empty_exact_target(target, sentinel)
            sentinel_backend_pid = int(preflight.pop("sentinelBackendPid"))

            # macOS exposes /tmp and /var through symlinks.  The production vault
            # deliberately rejects every symlink component, so resolve only the
            # harness-owned temporary parent before choosing the lexical vault path.
            private_temp_parent = Path(tempfile.gettempdir()).resolve(strict=True)
            with tempfile.TemporaryDirectory(
                prefix="caresync-family-authority-operator-cert-",
                dir=private_temp_parent,
            ) as temporary:
                work_root = Path(temporary)
                work_root.chmod(0o700)
                vault_root = work_root / "private-family-authority-vault"
                settings = Settings(
                    _env_file=None,
                    environment="test",
                    database_type="postgres",
                    database_host=target.host,
                    database_port=target.port,
                    database_user=target.runtime_user,
                    database_password=target.runtime_password,
                    database_name=target.database,
                    database_ssl=False,
                    database_read_only=False,
                    enable_advanced_routes=False,
                    jwt_secret=secrets.token_urlsafe(48),
                    family_evidence_vault_path=vault_root,
                    family_evidence_scanner_path=scanner,
                )
                application = create_app(settings)
                try:
                    with TestClient(application, raise_server_exceptions=False) as client:
                        flow = _run_public_http_flow(
                            client,
                            attestation_engine=attestation_engine,
                            vault_root=vault_root,
                        )
                except FamilyAuthorityOperatorCertificationError:
                    raise
                except Exception as error:
                    raise FamilyAuthorityOperatorCertificationError(
                        "Signed-in public HTTP operator flow failed"
                    ) from error
                postflight = _postflight_exact_target(
                    target,
                    attestation_engine,
                    sentinel_backend_pid=sentinel_backend_pid,
                )
    except FamilyAuthorityOperatorCertificationError:
        raise
    except Exception as error:
        raise FamilyAuthorityOperatorCertificationError(
            "Scratch PostgreSQL sentinel attestation failed"
        ) from error
    finally:
        attestation_engine.dispose()

    return {
        "format": CERTIFICATION_FORMAT,
        "generatedAt": datetime.now(UTC).isoformat(),
        "result": "passed",
        "scope": {
            "syntheticOnly": True,
            "publicHttpRoutes": True,
            "inProcessAsgi": True,
            "attestationSentinelHeld": True,
            "callerProvisionedDatabase": True,
            "databaseProvisionedByHarness": False,
            "alembicInvoked": False,
            "databaseDroppedOrTruncated": False,
            "protectedPortsContacted": False,
            "retainedDataAccessed": False,
            "releaseAuthority": False,
            "cutoverAuthority": False,
        },
        "target": {
            "hostClass": "loopback",
            "databaseName": target.database,
            "runtimeRole": target.runtime_user,
            **preflight,
            **postflight,
        },
        "scanner": {
            "engine": flow["scannerEngine"],
            "version": flow["scannerVersion"],
            "executableName": scanner.name,
            "definitionFreshnessEnforced": True,
        },
        "cases": {
            "ownerRegistration": True,
            "administratorInvitationActivation": True,
            "productionMultipartUpload": True,
            "uploadExactReplayNoDuplicateObject": True,
            "productionClamscanClean": True,
            "scanExactReplayNoDuplicateAssessment": True,
            "cleanDocumentDownload": True,
            "evidenceRecorded": True,
            "makerReviewRejected409": True,
            "makerReviewNoWriteAttested": True,
            "independentCheckerReview": True,
            "reviewedAuthorityActivation": flow["authorityRevision"] == 1,
            "activationExactReplayNoDuplicateRows": True,
            "piiFreeRealtimeInvalidation": True,
            "publicRealtimeWebSocketReplay": True,
            "administrativeSummaryObserved": True,
        },
        "redaction": {
            "credentialsRecorded": False,
            "tokensRecorded": False,
            "emailsRecorded": False,
            "personNamesRecorded": False,
            "recordIdentifiersRecorded": False,
            "documentBytesRecorded": False,
            "vaultPathsRecorded": False,
            "databaseDataDirectoryRecorded": False,
            "scannerAbsolutePathRecorded": False,
        },
    }


def write_private_operator_receipt(path: Path, payload: dict[str, Any]) -> Path:
    if not path.is_absolute():
        raise FamilyAuthorityOperatorCertificationError(
            "Certification receipt path must be absolute"
        )
    absolute = _absolute_lexical(path)
    backend_root = _absolute_lexical(BACKEND_ROOT)
    if absolute == backend_root or backend_root in absolute.parents:
        raise FamilyAuthorityOperatorCertificationError(
            "Certification receipt must remain outside the backend source tree"
        )
    _validate_completed_receipt_payload(payload)
    try:
        write_reconcile_report(absolute, payload)
    except EvidenceVaultReconcileError as error:
        raise FamilyAuthorityOperatorCertificationError(
            "Certification receipt could not be written privately without clobbering"
        ) from error
    details = absolute.stat(follow_symlinks=False)
    expected_owner = os.geteuid() if hasattr(os, "geteuid") else details.st_uid
    if (
        not stat.S_ISREG(details.st_mode)
        or stat.S_IMODE(details.st_mode) != 0o600
        or details.st_nlink != 1
        or details.st_uid != expected_owner
    ):
        raise FamilyAuthorityOperatorCertificationError(
            "Certification receipt did not remain a private single-link file"
        )
    return absolute


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Certify the signed-in family-authority flow on empty scratch 0029D."
    )
    parser.add_argument("--synthetic-only", action="store_true")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--database", default=DATABASE_NAME)
    parser.add_argument("--runtime-user", default=RUNTIME_ROLE)
    parser.add_argument("--attestation-user", required=True)
    parser.add_argument("--expected-data-directory", type=Path, required=True)
    parser.add_argument("--expected-system-identifier", required=True)
    parser.add_argument("--scanner", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    if not args.synthetic_only:
        parser.error("--synthetic-only is required")
    target = CertificationTarget(
        host=args.host.strip().lower(),
        port=args.port,
        database=args.database,
        runtime_user=args.runtime_user,
        runtime_password=os.getenv("CARESYNC_FAMILY_AUTHORITY_CERT_RUNTIME_PASSWORD", ""),
        attestation_user=args.attestation_user,
        attestation_password=os.getenv("CARESYNC_FAMILY_AUTHORITY_CERT_ATTESTATION_PASSWORD", ""),
        expected_data_directory=args.expected_data_directory,
        expected_system_identifier=args.expected_system_identifier,
    )
    try:
        payload = certify_family_authority_operator_flow(
            target,
            args.scanner,
            opt_in=os.getenv(OPT_IN_ENVIRONMENT),
            confirmation=os.getenv(CONFIRMATION_ENVIRONMENT),
        )
        receipt = write_private_operator_receipt(args.receipt, payload)
    except FamilyAuthorityOperatorCertificationError as error:
        parser.error(str(error))
    print(json.dumps({"result": "passed", "receipt": os.fspath(receipt)}))


if __name__ == "__main__":
    main()
