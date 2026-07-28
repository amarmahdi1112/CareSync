"""Certify bounded 0029D database/evidence-vault recovery consistency.

This command proves that a disposable PostgreSQL restore and a new private
evidence-vault restore match one verified four-artifact set.  It deliberately
does *not* prove that writers were quiescent while those source artifacts were
captured, that unreferenced source-vault files were absent, or that the schema
was produced by trusted migration code.  Its receipt therefore grants no
cutover, release, or purge authority.

The PostgreSQL target must be caller-provisioned and caller-migrated.  This
module never invokes Alembic and always delegates with
``prepare_empty_target=False``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import MetaData, func, select, text

from app.core.config import Settings
from app.db.session import Database
from scripts.backup_database import (
    BackupContractError,
    _json_line,
    _ordered_select,
    encode_value,
    verify_backup_artifacts,
)
from scripts.family_evidence_vault_bundle import (
    ASSESSMENT_TABLE,
    EVIDENCE_RESTORE_RECEIPT_FORMAT,
    OBJECT_TABLE,
    EvidenceVaultBundleError,
    derive_evidence_inventory_from_rows,
    restore_evidence_bundle,
    verify_evidence_bundle,
)
from scripts.family_evidence_vault_reconcile import (
    EvidenceVaultReconcileError,
    reconcile_evidence_vault,
)
from scripts.restore_database import (
    RestoreContractError,
    disposable_confirmation,
    restore_and_verify,
    validate_disposable_target,
    write_private_restore_receipt,
)

CERTIFICATION_FORMAT = "caresync-family-authority-joint-recovery-certification-v1"
DISPOSABLE_MARKER_FORMAT = "caresync-joint-recovery-target-v1"
DISPOSABLE_MARKER_NAME = ".caresync-joint-recovery-target.json"
DISPOSABLE_DATA_DIRECTORY_PREFIX = "caresync-joint-recovery-target."
REQUIRED_REVISION = "0029D_release_checkout_writer"
CONFIRMATION_ENV = "CARESYNC_JOINT_RECOVERY_CONFIRM_DISPOSABLE"


class JointRecoveryCertificationError(RuntimeError):
    """Raised when the bounded joint recovery proof cannot close."""


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _digest_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _absolute_lexical(path: Path) -> Path:
    return Path(os.path.abspath(path.expanduser()))


def _canonical_input_path(path: Path, *, label: str) -> Path:
    raw = Path(path)
    if not raw.is_absolute():
        raise JointRecoveryCertificationError(f"{label} must be an absolute path")
    if any(part in {".", ".."} or part.startswith("~") for part in raw.parts):
        raise JointRecoveryCertificationError(
            f"{label} cannot contain dot traversal or home-expansion components"
        )
    absolute = Path(os.path.abspath(os.fspath(raw)))
    _assert_no_symlink_components(absolute, label=label)
    return absolute


def _assert_no_symlink_components(path: Path, *, label: str) -> None:
    absolute = _absolute_lexical(path)
    cursor = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        cursor = cursor / part
        if os.path.lexists(cursor) and stat.S_ISLNK(cursor.lstat().st_mode):
            raise JointRecoveryCertificationError(f"{label} contains a symbolic link")


def _require_private_regular(path: Path, *, label: str) -> os.stat_result:
    _assert_no_symlink_components(path, label=label)
    try:
        details = path.lstat()
    except OSError as error:
        raise JointRecoveryCertificationError(f"{label} is absent") from error
    if (
        not stat.S_ISREG(details.st_mode)
        or stat.S_IMODE(details.st_mode) != 0o600
        or details.st_nlink != 1
        or details.st_uid != os.geteuid()
    ):
        raise JointRecoveryCertificationError(
            f"{label} must be an owner-controlled mode 0600 single-link file"
        )
    return details


def _stable_private_sha256(path: Path, *, label: str) -> str:
    lexical = _canonical_input_path(path, label=label)
    expected = _require_private_regular(lexical, label=label)
    flags = os.O_RDONLY | os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    try:
        descriptor = os.open(lexical, flags)
    except OSError as error:
        raise JointRecoveryCertificationError(f"{label} could not be opened safely") from error
    digest = hashlib.sha256()
    try:
        before = os.fstat(descriptor)
        if (before.st_dev, before.st_ino) != (expected.st_dev, expected.st_ino):
            raise JointRecoveryCertificationError(f"{label} changed before hashing")
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    current = lexical.lstat()
    before_identity = (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_nlink,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    if before_identity != (
        after.st_dev,
        after.st_ino,
        after.st_mode,
        after.st_nlink,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    ) or before_identity != (
        current.st_dev,
        current.st_ino,
        current.st_mode,
        current.st_nlink,
        current.st_size,
        current.st_mtime_ns,
        current.st_ctime_ns,
    ):
        raise JointRecoveryCertificationError(f"{label} changed while it was hashed")
    return digest.hexdigest()


def _require_private_parent(path: Path, *, label: str) -> None:
    parent = _absolute_lexical(path).parent
    _assert_no_symlink_components(parent, label=f"{label} parent")
    try:
        details = parent.lstat()
    except OSError as error:
        raise JointRecoveryCertificationError(f"{label} parent is absent") from error
    if (
        not stat.S_ISDIR(details.st_mode)
        or stat.S_IMODE(details.st_mode) != 0o700
        or details.st_uid != os.geteuid()
    ):
        raise JointRecoveryCertificationError(
            f"{label} parent must be an owner-controlled mode 0700 directory"
        )


def _load_json_without_duplicates(path: Path, *, label: str) -> dict[str, Any]:
    try:
        serialized = path.read_bytes()
    except OSError as error:
        raise JointRecoveryCertificationError(f"{label} is not valid JSON") from error
    return _parse_json_without_duplicates(serialized, label=label)


def _parse_json_without_duplicates(serialized: bytes, *, label: str) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise JointRecoveryCertificationError(f"{label} contains a duplicate JSON key")
            value[key] = item
        return value

    try:
        value = json.loads(serialized.decode("utf-8"), object_pairs_hook=reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise JointRecoveryCertificationError(f"{label} is not valid JSON") from error
    if not isinstance(value, dict):
        raise JointRecoveryCertificationError(f"{label} must be a JSON object")
    return value


def _load_stable_private_json(
    path: Path,
    *,
    label: str,
) -> tuple[dict[str, Any], bytes, str]:
    """Read, parse, and hash one small receipt through a stable no-follow inode."""

    lexical = _canonical_input_path(path, label=label)
    expected = _require_private_regular(lexical, label=label)
    if expected.st_size > 1024 * 1024:
        raise JointRecoveryCertificationError(f"{label} exceeds its receipt size bound")
    flags = os.O_RDONLY | os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    try:
        descriptor = os.open(lexical, flags)
    except OSError as error:
        raise JointRecoveryCertificationError(f"{label} could not be opened safely") from error
    try:
        before = os.fstat(descriptor)
        if (before.st_dev, before.st_ino) != (expected.st_dev, expected.st_ino):
            raise JointRecoveryCertificationError(f"{label} changed before reading")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, 64 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > 1024 * 1024:
                raise JointRecoveryCertificationError(
                    f"{label} exceeds its receipt size bound"
                )
            chunks.append(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    current = lexical.lstat()
    before_identity = (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_nlink,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    if before_identity != (
        after.st_dev,
        after.st_ino,
        after.st_mode,
        after.st_nlink,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    ) or before_identity != (
        current.st_dev,
        current.st_ino,
        current.st_mode,
        current.st_nlink,
        current.st_size,
        current.st_mtime_ns,
        current.st_ctime_ns,
    ):
        raise JointRecoveryCertificationError(f"{label} changed while it was read")
    serialized = b"".join(chunks)
    return (
        _parse_json_without_duplicates(serialized, label=label),
        serialized,
        hashlib.sha256(serialized).hexdigest(),
    )


def _open_directory_no_follow(path: Path, *, label: str) -> int:
    absolute = _absolute_lexical(path)
    if not hasattr(os, "O_DIRECTORY") or not hasattr(os, "O_NOFOLLOW"):
        raise JointRecoveryCertificationError(
            "This platform cannot safely synchronize private directories"
        )
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    current = os.open(absolute.anchor, flags)
    try:
        for part in absolute.parts[1:]:
            child = os.open(part, flags, dir_fd=current)
            os.close(current)
            current = child
        return current
    except OSError as error:
        os.close(current)
        raise JointRecoveryCertificationError(f"{label} is unsafe") from error


def _fsync_created_directory(path: Path, *, label: str) -> None:
    directory_descriptor = _open_directory_no_follow(path, label=label)
    parent_descriptor = _open_directory_no_follow(path.parent, label=f"{label} parent")
    try:
        os.fsync(directory_descriptor)
        os.fsync(parent_descriptor)
    except OSError as error:
        raise JointRecoveryCertificationError(
            f"{label} could not be durably created"
        ) from error
    finally:
        os.close(directory_descriptor)
        os.close(parent_descriptor)


def _ensure_private_output_directory(path: Path, *, label: str) -> Path:
    absolute = _absolute_lexical(path)
    _assert_no_symlink_components(absolute, label=label)
    if not os.path.lexists(absolute):
        missing: list[Path] = []
        cursor = absolute
        while not os.path.lexists(cursor):
            missing.append(cursor)
            parent = cursor.parent
            if parent == cursor:
                raise JointRecoveryCertificationError(f"{label} has no existing ancestor")
            cursor = parent
        if cursor.is_symlink() or not cursor.is_dir():
            raise JointRecoveryCertificationError(f"{label} has an unsafe ancestor")
        for directory in reversed(missing):
            try:
                directory.mkdir(mode=0o700)
            except FileExistsError as error:
                raise JointRecoveryCertificationError(
                    f"{label} changed while it was created"
                ) from error
            directory.chmod(0o700)
            _fsync_created_directory(directory, label=label)
    details = absolute.lstat()
    if (
        not stat.S_ISDIR(details.st_mode)
        or stat.S_IMODE(details.st_mode) != 0o700
        or details.st_uid != os.geteuid()
    ):
        raise JointRecoveryCertificationError(
            f"{label} must be an owner-controlled mode 0700 directory"
        )
    _assert_no_symlink_components(absolute, label=label)
    return absolute


def _validate_disposable_data_directory(
    expected_data_directory: Path,
    *,
    expected_system_identifier: str,
    database_name: str,
) -> Path:
    if not expected_system_identifier.isascii() or not expected_system_identifier.isdigit():
        raise JointRecoveryCertificationError(
            "Expected PostgreSQL system identifier must be an ASCII decimal value"
        )
    if not expected_data_directory.expanduser().is_absolute():
        raise JointRecoveryCertificationError("Expected PostgreSQL data directory must be absolute")
    absolute = _absolute_lexical(expected_data_directory)
    _assert_no_symlink_components(absolute, label="Expected PostgreSQL data directory")
    try:
        details = absolute.lstat()
    except OSError as error:
        raise JointRecoveryCertificationError(
            "Expected PostgreSQL data directory is absent"
        ) from error
    if (
        not stat.S_ISDIR(details.st_mode)
        or stat.S_IMODE(details.st_mode) != 0o700
        or details.st_uid != os.geteuid()
    ):
        raise JointRecoveryCertificationError(
            "Expected PostgreSQL data directory must be owner-controlled mode 0700"
        )
    resolved = absolute.resolve(strict=True)
    allowed_roots = {
        candidate.resolve(strict=True)
        for candidate in (Path("/tmp"), Path("/private/tmp"))
        if candidate.is_dir()
    }
    if (
        resolved.parent not in allowed_roots
        or not resolved.name.startswith(DISPOSABLE_DATA_DIRECTORY_PREFIX)
    ):
        raise JointRecoveryCertificationError(
            "Disposable PostgreSQL data directory must be a dedicated "
            f"/tmp/{DISPOSABLE_DATA_DIRECTORY_PREFIX}* scratch cluster"
        )
    for name in ("PG_VERSION", "postmaster.pid"):
        candidate = absolute / name
        _assert_no_symlink_components(candidate, label=f"PostgreSQL {name}")
        try:
            candidate_details = candidate.lstat()
        except OSError as error:
            raise JointRecoveryCertificationError(f"PostgreSQL {name} is absent") from error
        if (
            not stat.S_ISREG(candidate_details.st_mode)
            or candidate_details.st_nlink != 1
            or candidate_details.st_uid != os.geteuid()
        ):
            raise JointRecoveryCertificationError(f"PostgreSQL {name} is unsafe")

    marker_path = absolute / DISPOSABLE_MARKER_NAME
    _require_private_regular(marker_path, label="Disposable target marker")
    marker = _load_json_without_duplicates(marker_path, label="Disposable target marker")
    expected_marker = {
        "format": DISPOSABLE_MARKER_FORMAT,
        "purpose": "0029D-artifact-recovery-consistency",
        "databaseName": database_name,
        "systemIdentifier": expected_system_identifier,
    }
    if marker != expected_marker:
        raise JointRecoveryCertificationError(
            "Disposable target marker does not identify the expected cluster"
        )
    return resolved


def joint_disposable_confirmation(
    settings: Settings,
    *,
    expected_data_directory: Path,
    expected_system_identifier: str,
    backup_sha256: str,
    manifest_sha256: str,
    bundle_sha256: str,
    bundle_manifest_sha256: str,
) -> str:
    identity = {
        "endpoint": disposable_confirmation(settings),
        "dataDirectorySha256": hashlib.sha256(
            os.fspath(_absolute_lexical(expected_data_directory)).encode("utf-8")
        ).hexdigest(),
        "systemIdentifier": expected_system_identifier,
        "backupSha256": backup_sha256,
        "manifestSha256": manifest_sha256,
        "bundleSha256": bundle_sha256,
        "bundleManifestSha256": bundle_manifest_sha256,
    }
    return f"CONFIRM-CARESYNC-0029D-JOINT-RECOVERY:{_digest_json(identity)}"


def _normal_inventory_value(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    return value


def _inventory_rows(connection: Any, metadata: MetaData) -> list[dict[str, Any]]:
    object_table = metadata.tables.get(OBJECT_TABLE)
    assessment_table = metadata.tables.get(ASSESSMENT_TABLE)
    if object_table is None or assessment_table is None:
        raise JointRecoveryCertificationError(
            "Restored target lacks the 0029A1 evidence-vault tables"
        )
    object_fields = (
        "id",
        "organization_id",
        "family_id",
        "evidence_kind",
        "object_version",
        "storage_reference",
        "media_type",
        "byte_size",
        "content_sha256",
        "status",
    )
    assessment_fields = (
        "organization_id",
        "family_id",
        "evidence_object_id",
        "version_number",
        "decision",
        "reason_code",
    )
    object_rows = [
        {key: _normal_inventory_value(row[key]) for key in object_fields}
        for row in connection.execute(
            select(*(object_table.c[key] for key in object_fields)).order_by(object_table.c.id)
        ).mappings()
    ]
    assessment_rows = [
        {key: _normal_inventory_value(row[key]) for key in assessment_fields}
        for row in connection.execute(
            select(*(assessment_table.c[key] for key in assessment_fields)).order_by(
                assessment_table.c.evidence_object_id,
                assessment_table.c.version_number,
            )
        ).mappings()
    ]
    try:
        return derive_evidence_inventory_from_rows(object_rows, assessment_rows)
    except EvidenceVaultBundleError as error:
        raise JointRecoveryCertificationError(str(error)) from error


def _database_row_digest(connection: Any, metadata: MetaData) -> str:
    digest = hashlib.sha256()
    for table_name, table in sorted(metadata.tables.items()):
        for row in connection.execute(_ordered_select(table)).mappings():
            line = _json_line(
                {
                    "table": table_name,
                    "row": {key: encode_value(value) for key, value in row.items()},
                }
            )
            digest.update(line.encode("utf-8"))
    return digest.hexdigest()


def _observe_target(
    settings: Settings,
    *,
    expected_tables: list[str],
    expected_revision: str,
    require_empty: bool,
    include_inventory: bool,
) -> dict[str, Any]:
    database = Database(settings)
    try:
        with (
            database.engine.connect().execution_options(isolation_level="REPEATABLE READ")
            as connection,
            connection.begin(),
        ):
            connection.exec_driver_sql("SET TRANSACTION READ ONLY, DEFERRABLE")
            connection.exec_driver_sql("SET LOCAL row_security = off")
            connection.exec_driver_sql("SET LOCAL TIME ZONE 'UTC'")
            role = (
                connection.execute(
                    text(
                        "SELECT role.rolsuper, role.rolbypassrls "
                        "FROM pg_roles AS role WHERE role.rolname=current_user"
                    )
                )
                .mappings()
                .one_or_none()
            )
            if role is None or not (bool(role["rolsuper"]) or bool(role["rolbypassrls"])):
                raise JointRecoveryCertificationError(
                    "Disposable recovery role must be superuser or BYPASSRLS"
                )
            identity = (
                connection.execute(
                    text(
                        "SELECT current_database() AS database_name, "
                        "COALESCE(host(inet_server_addr()),'') AS server_address, "
                        "inet_server_port() AS server_port, "
                        "current_setting('data_directory') AS data_directory, "
                        "pg_postmaster_start_time() AS postmaster_started_at"
                    )
                )
                .mappings()
                .one()
            )
            system_identifier = str(
                connection.execute(
                    text("SELECT system_identifier::text FROM pg_control_system()")
                ).scalar_one()
            )
            other_sessions = int(
                connection.execute(
                    text(
                        "SELECT count(*) FROM pg_stat_activity "
                        "WHERE datname=current_database() "
                        "AND backend_type='client backend' AND pid<>pg_backend_pid()"
                    )
                ).scalar_one()
            )
            if other_sessions:
                raise JointRecoveryCertificationError(
                    "Disposable target has another client session"
                )
            actual_tables = list(
                connection.execute(
                    text(
                        "SELECT class.relname FROM pg_class AS class "
                        "JOIN pg_namespace AS namespace ON namespace.oid=class.relnamespace "
                        "WHERE namespace.nspname='public' "
                        "AND class.relkind IN ('r','p') ORDER BY class.relname"
                    )
                ).scalars()
            )
            if actual_tables != expected_tables:
                raise JointRecoveryCertificationError(
                    "Disposable target table inventory does not match the backup"
                )
            metadata = MetaData()
            metadata.reflect(bind=connection)
            version_table = metadata.tables.get("alembic_version")
            revisions = (
                list(
                    connection.execute(
                        select(version_table.c.version_num).order_by(version_table.c.version_num)
                    ).scalars()
                )
                if version_table is not None
                else []
            )
            if revisions != [expected_revision]:
                raise JointRecoveryCertificationError(
                    "Disposable target Alembic revision does not match exact 0029D"
                )
            table_counts = {
                table_name: int(
                    connection.execute(select(func.count()).select_from(table)).scalar_one()
                )
                for table_name, table in sorted(metadata.tables.items())
            }
            non_revision_rows = sum(
                count
                for table_name, count in table_counts.items()
                if table_name != "alembic_version"
            )
            if require_empty and non_revision_rows:
                raise JointRecoveryCertificationError(
                    "Disposable target must contain no application rows before restore"
                )
            inventory = _inventory_rows(connection, metadata) if include_inventory else None
            row_digest = _database_row_digest(connection, metadata)
            started = identity["postmaster_started_at"]
            return {
                "databaseName": identity["database_name"],
                "serverAddress": identity["server_address"],
                "serverPort": identity["server_port"],
                "dataDirectory": identity["data_directory"],
                "systemIdentifier": system_identifier,
                "postmasterStartedAt": (
                    started.astimezone(UTC).isoformat()
                    if hasattr(started, "astimezone")
                    else str(started)
                ),
                "otherClientSessions": other_sessions,
                "tableCounts": table_counts,
                "applicationRows": non_revision_rows,
                "inventory": inventory,
                "sha256Rows": row_digest,
            }
    finally:
        database.dispose()


def _validate_target_identity(
    observation: dict[str, Any],
    settings: Settings,
    *,
    expected_data_directory: Path,
    expected_system_identifier: str,
) -> None:
    if observation.get("databaseName") != settings.database_name:
        raise JointRecoveryCertificationError("Connected PostgreSQL database identity changed")
    if observation.get("serverPort") != settings.database_port:
        raise JointRecoveryCertificationError("Connected PostgreSQL port identity changed")
    if observation.get("serverAddress") not in {"127.0.0.1", "::1"}:
        raise JointRecoveryCertificationError("Connected PostgreSQL server is not loopback")
    observed_directory = Path(str(observation.get("dataDirectory", "")))
    if _absolute_lexical(observed_directory) != expected_data_directory:
        raise JointRecoveryCertificationError("Connected PostgreSQL data directory is unexpected")
    if observation.get("systemIdentifier") != expected_system_identifier:
        raise JointRecoveryCertificationError(
            "Connected PostgreSQL system identifier is unexpected"
        )
    if observation.get("otherClientSessions") != 0:
        raise JointRecoveryCertificationError("Disposable target is not quiescent")


def _validate_recovery_paths(
    *,
    artifact_paths: tuple[Path, Path, Path, Path],
    expected_data_directory: Path,
    vault_destination: Path,
    database_receipt: Path,
    vault_receipt: Path,
    joint_receipt: Path,
) -> None:
    artifacts = [_absolute_lexical(path) for path in artifact_paths]
    outputs = [
        _absolute_lexical(database_receipt),
        _absolute_lexical(vault_receipt),
        _absolute_lexical(joint_receipt),
    ]
    destination = _absolute_lexical(vault_destination)
    data_directory = _absolute_lexical(expected_data_directory)
    relevant = [*artifacts, *outputs, destination, data_directory]
    if len(set(relevant)) != len(relevant):
        raise JointRecoveryCertificationError("Recovery paths must be pairwise distinct")
    artifact_identities = {
        (path.lstat().st_dev, path.lstat().st_ino) for path in artifacts
    }
    if len(artifact_identities) != len(artifacts):
        raise JointRecoveryCertificationError("Recovery artifacts alias one filesystem object")
    if os.path.lexists(destination):
        raise JointRecoveryCertificationError(
            "Disposable evidence restore destination already exists"
        )
    for path in outputs:
        _assert_no_symlink_components(path, label="Recovery receipt path")
        if os.path.lexists(path):
            raise JointRecoveryCertificationError(
                "Recovery receipt path already exists; no artifact was restored"
            )
        if path == destination or destination in path.parents:
            raise JointRecoveryCertificationError(
                "Recovery receipts cannot be written inside the restored vault"
            )
    for path in [*artifacts, *outputs, destination]:
        if (
            path == data_directory
            or data_directory in path.parents
            or path in data_directory.parents
        ):
            raise JointRecoveryCertificationError(
                "Recovery artifacts, receipts, and vault destination must be outside PGDATA"
            )
    output_parents = {
        path.parent for path in [*outputs, destination]
    }
    for parent in sorted(output_parents, key=os.fspath):
        _ensure_private_output_directory(parent, label="Recovery output parent")


def _recheck_recovery_outputs(
    *,
    vault_destination: Path,
    database_receipt: Path,
    vault_receipt: Path,
    joint_receipt: Path,
) -> None:
    destination = _absolute_lexical(vault_destination)
    outputs = [
        _absolute_lexical(database_receipt),
        _absolute_lexical(vault_receipt),
        _absolute_lexical(joint_receipt),
    ]
    if os.path.lexists(destination) or any(os.path.lexists(path) for path in outputs):
        raise JointRecoveryCertificationError(
            "A recovery output appeared after preflight; no database restore was run"
        )
    for parent in sorted({path.parent for path in [*outputs, destination]}, key=os.fspath):
        _ensure_private_output_directory(parent, label="Recovery output parent")


def _require_exact_reconciliation(report: dict[str, Any], object_count: int) -> None:
    if report.get("expectedCount") != object_count or report.get("presentCount") != object_count:
        raise JointRecoveryCertificationError("Restored evidence inventory count is incomplete")
    for key in (
        "missing",
        "mismatched",
        "unexpected",
        "unsafe",
        "indeterminate",
        "unclassifiedDirectories",
    ):
        if report.get(key) != []:
            raise JointRecoveryCertificationError(
                f"Restored evidence vault has a non-empty {key} finding"
            )


def certify_joint_recovery(
    backup_path: Path,
    manifest_path: Path,
    bundle_path: Path,
    bundle_manifest_path: Path,
    *,
    expected_data_directory: Path,
    expected_system_identifier: str,
    vault_destination: Path,
    database_receipt: Path,
    vault_receipt: Path,
    joint_receipt: Path,
    confirmation: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Restore and close a bounded, explicitly non-cutover recovery proof."""

    backup_path = _canonical_input_path(backup_path, label="Database backup")
    manifest_path = _canonical_input_path(manifest_path, label="Database backup manifest")
    bundle_path = _canonical_input_path(bundle_path, label="Evidence bundle")
    bundle_manifest_path = _canonical_input_path(
        bundle_manifest_path,
        label="Evidence bundle manifest",
    )
    expected_data_directory = _canonical_input_path(
        expected_data_directory,
        label="Expected PostgreSQL data directory",
    )
    vault_destination = _canonical_input_path(
        vault_destination,
        label="Disposable evidence restore destination",
    )
    database_receipt = _canonical_input_path(
        database_receipt,
        label="Database restore receipt",
    )
    vault_receipt = _canonical_input_path(
        vault_receipt,
        label="Evidence restore receipt",
    )
    joint_receipt = _canonical_input_path(
        joint_receipt,
        label="Joint recovery receipt",
    )
    artifact_paths = (backup_path, manifest_path, bundle_path, bundle_manifest_path)
    artifact_labels = (
        "Database backup",
        "Database backup manifest",
        "Evidence bundle",
        "Evidence bundle manifest",
    )
    for path, label in zip(artifact_paths, artifact_labels, strict=True):
        _require_private_parent(path, label=label)
        _require_private_regular(path, label=label)
    artifact_hashes = {
        "databaseBackupSha256": _stable_private_sha256(
            backup_path,
            label="Database backup",
        ),
        "databaseManifestSha256": _stable_private_sha256(
            manifest_path,
            label="Database backup manifest",
        ),
        "evidenceBundleSha256": _stable_private_sha256(
            bundle_path,
            label="Evidence bundle",
        ),
        "evidenceBundleManifestSha256": _stable_private_sha256(
            bundle_manifest_path,
            label="Evidence bundle manifest",
        ),
    }
    try:
        configured = settings or Settings(database_read_only=False)
        validate_disposable_target(configured, disposable_confirmation(configured))
        backup = verify_backup_artifacts(backup_path, manifest_path)
        evidence = verify_evidence_bundle(
            backup_path,
            manifest_path,
            bundle_path,
            bundle_manifest_path,
        )
    except (BackupContractError, EvidenceVaultBundleError, RestoreContractError) as error:
        raise JointRecoveryCertificationError(str(error)) from error

    revisions = backup["header"].get("alembicRevisions")
    if revisions != [REQUIRED_REVISION]:
        raise JointRecoveryCertificationError(
            f"Joint recovery certification requires exact revision {REQUIRED_REVISION}"
        )
    if backup["header"].get("databaseType") != "postgres":
        raise JointRecoveryCertificationError("Joint recovery certification requires PostgreSQL")
    if artifact_hashes["databaseBackupSha256"] != backup["manifest"]["sha256Compressed"]:
        raise JointRecoveryCertificationError("Database backup raw digest is inconsistent")
    database_binding = evidence["manifest"].get("databaseBackup")
    if (
        not isinstance(database_binding, dict)
        or database_binding.get("sha256Compressed")
        != artifact_hashes["databaseBackupSha256"]
        or database_binding.get("sha256Manifest")
        != artifact_hashes["databaseManifestSha256"]
        or evidence["manifest"].get("sha256Bundle")
        != artifact_hashes["evidenceBundleSha256"]
    ):
        raise JointRecoveryCertificationError(
            "The four recovery artifacts do not share one exact database binding"
        )
    expected_tables = backup["header"].get("tables")
    if not isinstance(expected_tables, list) or any(
        not isinstance(item, str) for item in expected_tables
    ):
        raise JointRecoveryCertificationError("Backup table inventory is invalid")

    expected_directory = _validate_disposable_data_directory(
        expected_data_directory,
        expected_system_identifier=expected_system_identifier,
        database_name=configured.database_name,
    )
    _validate_recovery_paths(
        artifact_paths=artifact_paths,
        expected_data_directory=expected_directory,
        vault_destination=vault_destination,
        database_receipt=database_receipt,
        vault_receipt=vault_receipt,
        joint_receipt=joint_receipt,
    )
    expected_confirmation = joint_disposable_confirmation(
        configured,
        expected_data_directory=expected_directory,
        expected_system_identifier=expected_system_identifier,
        backup_sha256=artifact_hashes["databaseBackupSha256"],
        manifest_sha256=artifact_hashes["databaseManifestSha256"],
        bundle_sha256=artifact_hashes["evidenceBundleSha256"],
        bundle_manifest_sha256=artifact_hashes["evidenceBundleManifestSha256"],
    )
    supplied_confirmation = confirmation or os.environ.get(CONFIRMATION_ENV)
    if supplied_confirmation != expected_confirmation:
        raise JointRecoveryCertificationError(
            f"Exact disposable recovery confirmation is required: {expected_confirmation}"
        )

    try:
        preflight = _observe_target(
            configured,
            expected_tables=expected_tables,
            expected_revision=REQUIRED_REVISION,
            require_empty=True,
            include_inventory=False,
        )
    except JointRecoveryCertificationError:
        raise
    except Exception as error:
        raise JointRecoveryCertificationError(
            "Disposable PostgreSQL target preflight failed closed"
        ) from error
    _validate_target_identity(
        preflight,
        configured,
        expected_data_directory=expected_directory,
        expected_system_identifier=expected_system_identifier,
    )
    if preflight.get("applicationRows") != 0:
        raise JointRecoveryCertificationError(
            "Disposable target is not empty at certification preflight"
        )
    _recheck_recovery_outputs(
        vault_destination=vault_destination,
        database_receipt=database_receipt,
        vault_receipt=vault_receipt,
        joint_receipt=joint_receipt,
    )

    previous_restore_confirmation = os.environ.get("CARESYNC_RESTORE_CONFIRM_DISPOSABLE")
    os.environ["CARESYNC_RESTORE_CONFIRM_DISPOSABLE"] = disposable_confirmation(configured)
    try:
        database_result = restore_and_verify(
            backup_path,
            manifest_path,
            prepare_empty_target=False,
            receipt_path=database_receipt,
            expected_data_directory=expected_directory,
            expected_system_identifier=expected_system_identifier,
            require_empty_target=True,
            configured_settings=configured,
        )
    except (BackupContractError, RestoreContractError) as error:
        raise JointRecoveryCertificationError(str(error)) from error
    except Exception as error:
        raise JointRecoveryCertificationError(
            "Disposable PostgreSQL restore failed closed"
        ) from error
    finally:
        if previous_restore_confirmation is None:
            os.environ.pop("CARESYNC_RESTORE_CONFIRM_DISPOSABLE", None)
        else:
            os.environ["CARESYNC_RESTORE_CONFIRM_DISPOSABLE"] = previous_restore_confirmation

    try:
        vault_result = restore_evidence_bundle(
            backup_path,
            manifest_path,
            bundle_path,
            bundle_manifest_path,
            vault_destination,
            receipt_path=vault_receipt,
        )
        postflight = _observe_target(
            configured,
            expected_tables=expected_tables,
            expected_revision=REQUIRED_REVISION,
            require_empty=False,
            include_inventory=True,
        )
        _validate_target_identity(
            postflight,
            configured,
            expected_data_directory=expected_directory,
            expected_system_identifier=expected_system_identifier,
        )
        _validate_disposable_data_directory(
            expected_directory,
            expected_system_identifier=expected_system_identifier,
            database_name=configured.database_name,
        )
        report = reconcile_evidence_vault(
            backup_path,
            manifest_path,
            vault_destination,
        )
    except JointRecoveryCertificationError:
        raise
    except (EvidenceVaultBundleError, EvidenceVaultReconcileError) as error:
        raise JointRecoveryCertificationError(str(error)) from error
    except Exception as error:
        raise JointRecoveryCertificationError(
            "Joint database/vault postflight failed closed"
        ) from error

    if preflight["postmasterStartedAt"] != postflight["postmasterStartedAt"]:
        raise JointRecoveryCertificationError(
            "Disposable PostgreSQL cluster restarted during proof"
        )
    if database_result.get("alembicRevisions") != [REQUIRED_REVISION]:
        raise JointRecoveryCertificationError("Database restore receipt revision is unexpected")
    if database_result.get("strongTargetAttestation") != {
        "performed": True,
        "targetWasEmpty": True,
        "otherClientSessions": 0,
    }:
        raise JointRecoveryCertificationError(
            "Database restore did not close its same-transaction target attestation"
        )
    if database_result.get("tableCounts") != backup["manifest"]["tableCounts"]:
        raise JointRecoveryCertificationError("Database restore receipt counts are unexpected")
    if database_result.get("backupSha256") != backup["manifest"]["sha256Compressed"]:
        raise JointRecoveryCertificationError(
            "Database restore receipt backup digest is unexpected"
        )
    if database_result.get("sha256Rows") != backup["manifest"]["sha256Rows"]:
        raise JointRecoveryCertificationError("Database restore receipt row digest is unexpected")
    if postflight["tableCounts"] != backup["manifest"]["tableCounts"]:
        raise JointRecoveryCertificationError("Independent restored database counts differ")
    if postflight["sha256Rows"] != backup["manifest"]["sha256Rows"]:
        raise JointRecoveryCertificationError("Independent restored database row digest differs")
    if postflight["inventory"] != evidence["objects"]:
        raise JointRecoveryCertificationError(
            "Restored database evidence inventory differs from the vault bundle"
        )
    if _digest_json(postflight["inventory"]) != evidence["manifest"]["inventorySha256"]:
        raise JointRecoveryCertificationError(
            "Restored database evidence inventory digest differs from the vault bundle"
        )
    _require_exact_reconciliation(report, evidence["objectCount"])
    if (
        vault_result.get("inventorySha256") != evidence["manifest"]["inventorySha256"]
        or vault_result.get("bundleSha256") != evidence["manifest"]["sha256Bundle"]
        or vault_result.get("restoredObjectCount") != evidence["includedObjectCount"]
    ):
        raise JointRecoveryCertificationError("Evidence restore receipt is inconsistent")

    try:
        final_backup = verify_backup_artifacts(backup_path, manifest_path)
        final_evidence = verify_evidence_bundle(
            backup_path,
            manifest_path,
            bundle_path,
            bundle_manifest_path,
        )
    except (BackupContractError, EvidenceVaultBundleError) as error:
        raise JointRecoveryCertificationError(str(error)) from error
    if _digest_json(final_backup) != _digest_json(backup):
        raise JointRecoveryCertificationError("Database artifacts changed during recovery proof")
    if _digest_json(final_evidence) != _digest_json(evidence):
        raise JointRecoveryCertificationError("Evidence artifacts changed during recovery proof")
    for path, label in zip(artifact_paths, artifact_labels, strict=True):
        _require_private_parent(path, label=label)
        _require_private_regular(path, label=label)
    final_artifact_hashes = {
        "databaseBackupSha256": _stable_private_sha256(
            backup_path,
            label="Database backup",
        ),
        "databaseManifestSha256": _stable_private_sha256(
            manifest_path,
            label="Database backup manifest",
        ),
        "evidenceBundleSha256": _stable_private_sha256(
            bundle_path,
            label="Evidence bundle",
        ),
        "evidenceBundleManifestSha256": _stable_private_sha256(
            bundle_manifest_path,
            label="Evidence bundle manifest",
        ),
    }
    if final_artifact_hashes != artifact_hashes:
        raise JointRecoveryCertificationError(
            "One of the four recovery artifacts changed at the byte level"
        )

    (
        database_receipt_value,
        database_receipt_bytes,
        database_receipt_sha256,
    ) = _load_stable_private_json(
        database_receipt,
        label="Database restore receipt",
    )
    expected_database_receipt_bytes = (
        json.dumps(database_result, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    expected_database_receipt_keys = {
        "format",
        "verifiedAt",
        "backup",
        "backupSha256",
        "target",
        "alembicRevisions",
        "tableCounts",
        "totalRows",
        "sha256Rows",
        "strongTargetAttestation",
    }
    if (
        set(database_receipt_value) != expected_database_receipt_keys
        or database_receipt_value != database_result
        or database_receipt_bytes != expected_database_receipt_bytes
    ):
        raise JointRecoveryCertificationError(
            "Database restore receipt is not the expected closed-shape result"
        )
    if (
        database_receipt_value["format"] != "caresync-restore-verification-v1"
        or database_receipt_value["backup"] != backup_path.name
        or database_receipt_value["backupSha256"]
        != backup["manifest"]["sha256Compressed"]
        or database_receipt_value["target"] != disposable_confirmation(configured)
        or database_receipt_value["totalRows"] != backup["manifest"]["totalRows"]
    ):
        raise JointRecoveryCertificationError(
            "Database restore receipt identity fields are inconsistent"
        )
    (
        vault_receipt_value,
        vault_receipt_bytes,
        vault_receipt_sha256,
    ) = _load_stable_private_json(
        vault_receipt,
        label="Evidence restore receipt",
    )
    expected_vault_receipt_bytes = (
        json.dumps(vault_result, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    expected_vault_receipt_keys = {
        "format",
        "verifiedAt",
        "databaseBackup",
        "bundle",
        "bundleSha256",
        "inventorySha256",
        "objectCount",
        "restoredObjectCount",
        "rejectedObjectCount",
    }
    if (
        set(vault_receipt_value) != expected_vault_receipt_keys
        or vault_receipt_value != vault_result
        or vault_receipt_bytes != expected_vault_receipt_bytes
    ):
        raise JointRecoveryCertificationError(
            "Evidence restore receipt is not the expected closed-shape result"
        )
    if (
        vault_receipt_value["format"] != EVIDENCE_RESTORE_RECEIPT_FORMAT
        or vault_receipt_value["databaseBackup"]
        != evidence["manifest"]["databaseBackup"]
        or vault_receipt_value["bundle"] != bundle_path.name
        or vault_receipt_value["objectCount"] != evidence["objectCount"]
        or vault_receipt_value["rejectedObjectCount"] != evidence["rejectedObjectCount"]
    ):
        raise JointRecoveryCertificationError(
            "Evidence restore receipt identity fields are inconsistent"
        )
    snapshot_binding = {
        "databaseBackupSha256": artifact_hashes["databaseBackupSha256"],
        "databaseManifestSha256": artifact_hashes["databaseManifestSha256"],
        "databaseRowsSha256": backup["manifest"]["sha256Rows"],
        "evidenceBundleSha256": artifact_hashes["evidenceBundleSha256"],
        "evidenceBundleManifestSha256": artifact_hashes[
            "evidenceBundleManifestSha256"
        ],
        "evidenceInventorySha256": evidence["manifest"]["inventorySha256"],
        "alembicRevision": REQUIRED_REVISION,
    }
    result = {
        "format": CERTIFICATION_FORMAT,
        "certifiedAt": datetime.now(UTC).isoformat(),
        "result": "passed",
        "scope": {
            "artifactRecoveryConsistencyOnly": True,
            "recoveryConsistencyProven": True,
            "sourceWriterQuiescenceProven": False,
            "authoritativeSourceCompletenessProven": False,
            "authoritativeSameSnapshotCaptureProven": False,
            "sourceVaultUnexpectedEntriesRuledOut": False,
            "targetSchemaAuthenticityProven": False,
            "cutoverAuthority": False,
            "releaseAuthority": False,
            "purgeAuthority": False,
            "migrationInvoked": False,
        },
        "snapshot": {
            **snapshot_binding,
            "commonArtifactIdentitySha256": _digest_json(snapshot_binding),
        },
        "restores": {
            "databaseReceiptSha256": database_receipt_sha256,
            "evidenceReceiptSha256": vault_receipt_sha256,
            "databaseTableCount": len(database_result["tableCounts"]),
            "databaseTotalRows": database_result["totalRows"],
            "evidenceObjectCount": evidence["objectCount"],
            "rejectedEvidenceObjectCount": evidence["rejectedObjectCount"],
        },
        "disposableTarget": {
            "hostClass": "loopback",
            "databaseName": configured.database_name,
            "protectedPortUsed": False,
            "preflightApplicationRows": preflight["applicationRows"],
            "preflightOtherClientSessions": preflight["otherClientSessions"],
            "postflightOtherClientSessions": postflight["otherClientSessions"],
            "sameClusterIdentity": True,
            "systemIdentifierSha256": hashlib.sha256(
                expected_system_identifier.encode("utf-8")
            ).hexdigest(),
            "dataDirectorySha256": hashlib.sha256(
                os.fspath(expected_directory).encode("utf-8")
            ).hexdigest(),
        },
    }
    try:
        write_private_restore_receipt(joint_receipt, result)
        joint_receipt_value, joint_receipt_bytes, _ = _load_stable_private_json(
            joint_receipt,
            label="Joint recovery receipt",
        )
        expected_joint_receipt_bytes = (
            json.dumps(result, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        if joint_receipt_value != result or joint_receipt_bytes != expected_joint_receipt_bytes:
            raise JointRecoveryCertificationError(
                "Joint recovery receipt does not match its closed decision"
            )
    except RestoreContractError as error:
        raise JointRecoveryCertificationError(str(error)) from error
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--bundle-manifest", type=Path, required=True)
    parser.add_argument("--expected-pgdata", type=Path, required=True)
    parser.add_argument("--expected-system-identifier", required=True)
    parser.add_argument("--vault-destination", type=Path, required=True)
    parser.add_argument("--database-receipt", type=Path, required=True)
    parser.add_argument("--vault-receipt", type=Path, required=True)
    parser.add_argument("--joint-receipt", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = certify_joint_recovery(
            args.backup,
            args.manifest,
            args.bundle,
            args.bundle_manifest,
            expected_data_directory=args.expected_pgdata,
            expected_system_identifier=args.expected_system_identifier,
            vault_destination=args.vault_destination,
            database_receipt=args.database_receipt,
            vault_receipt=args.vault_receipt,
            joint_receipt=args.joint_receipt,
        )
    except JointRecoveryCertificationError as error:
        parser.error(str(error))
    print(
        "0029D artifact recovery consistency certified; "
        f"cutover authority={result['scope']['cutoverAuthority']}"
    )


if __name__ == "__main__":
    main()
