"""Report-only preflight for the encrypted staff and transport evidence vault.

Only a verified logical database backup may define the expected inventory. The
tool never opens a database, decrypts evidence, reads key bytes, or mutates the
vault. Vault traversal is descriptor-relative and does not follow symbolic
links. The resulting private receipt is deliberately not consistency or purge
authority because the backup contract has no proved snapshot boundary.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import re
import stat
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import UUID

from scripts.backup_database import BackupContractError, verify_backup_artifacts

PREFLIGHT_FORMAT = "caresync-staff-transport-vault-preflight-v1"
BLOCKER = "snapshot_boundary_unproven"
EVIDENCE_TABLES = (
    "staff_screening_document_versions",
    "staff_driver_qualification_evidence_objects",
    "transport_vehicle_evidence_versions",
)
READ_CHUNK_BYTES = 1024 * 1024
MAXIMUM_PLAINTEXT_BYTES = 50 * 1024 * 1024
ENCRYPTED_CONTAINER_OVERHEAD_BYTES = 8 + 12 + 16
MAXIMUM_CIPHERTEXT_BYTES = MAXIMUM_PLAINTEXT_BYTES + ENCRYPTED_CONTAINER_OVERHEAD_BYTES
MAXIMUM_MANIFEST_BYTES = 8 * 1024 * 1024
LOWERCASE_SHA256 = re.compile(r"^[0-9a-f]{64}$")
CANONICAL_COMPONENT = re.compile(r"^[0-9a-f]{32}$")
VEHICLE_EVIDENCE_STATUSES = {
    "provided",
    "verified",
    "rejected",
    "expired",
    "revoked",
}


class StaffTransportVaultPreflightError(RuntimeError):
    """Raised when a safe report cannot be derived."""


class _MeasurementIssue(RuntimeError):
    def __init__(self, reason: str, *, indeterminate: bool) -> None:
        super().__init__(reason)
        self.reason = reason
        self.indeterminate = indeterminate


@dataclass(frozen=True)
class _NodeRecord:
    reference: str
    device: int
    inode: int
    mode: int
    owner: int
    links: int
    size: int
    modified_ns: int
    changed_ns: int


@dataclass(frozen=True)
class _PinnedArtifact:
    path: Path
    parent_descriptor: int
    descriptor: int
    details: os.stat_result

    def close(self) -> None:
        os.close(self.descriptor)
        os.close(self.parent_descriptor)


def _absolute_lexical(path: Path) -> Path:
    return Path(os.path.abspath(path.expanduser()))


def _mode(value: os.stat_result) -> int:
    return stat.S_IMODE(value.st_mode)


def _stable_stat(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_uid,
        value.st_nlink,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _node_record(reference: str, value: os.stat_result) -> _NodeRecord:
    return _NodeRecord(
        reference=reference,
        device=value.st_dev,
        inode=value.st_ino,
        mode=_mode(value),
        owner=value.st_uid,
        links=value.st_nlink,
        size=value.st_size,
        modified_ns=value.st_mtime_ns,
        changed_ns=value.st_ctime_ns,
    )


def _record_matches(record: _NodeRecord, value: os.stat_result) -> bool:
    return (
        record.device,
        record.inode,
        record.mode,
        record.owner,
        record.links,
        record.size,
        record.modified_ns,
        record.changed_ns,
    ) == (
        value.st_dev,
        value.st_ino,
        _mode(value),
        value.st_uid,
        value.st_nlink,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _require_descriptor_primitives() -> None:
    if not hasattr(os, "O_DIRECTORY") or not hasattr(os, "O_NOFOLLOW"):
        raise StaffTransportVaultPreflightError(
            "This platform cannot provide descriptor-relative no-follow traversal"
        )
    if (
        os.open not in os.supports_dir_fd
        or os.scandir not in os.supports_fd
        or os.stat not in os.supports_dir_fd
    ):
        raise StaffTransportVaultPreflightError(
            "This platform cannot provide descriptor-relative no-follow traversal"
        )


def _directory_flags() -> int:
    _require_descriptor_primitives()
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    return flags


def _file_flags() -> int:
    _require_descriptor_primitives()
    flags = os.O_RDONLY | os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    return flags


def _open_directory_path_no_follow(
    path: Path,
    *,
    label: str,
    forbidden_identity: tuple[int, int] | None = None,
) -> int:
    absolute = _absolute_lexical(path)
    current = os.open(absolute.anchor, _directory_flags())
    try:
        details = os.fstat(current)
        if forbidden_identity == (details.st_dev, details.st_ino):
            raise StaffTransportVaultPreflightError(f"{label} includes the scanned evidence vault")
        for part in absolute.parts[1:]:
            child = os.open(part, _directory_flags(), dir_fd=current)
            os.close(current)
            current = child
            details = os.fstat(current)
            if forbidden_identity == (details.st_dev, details.st_ino):
                raise StaffTransportVaultPreflightError(
                    f"{label} includes the scanned evidence vault"
                )
        return current
    except FileNotFoundError:
        os.close(current)
        raise
    except StaffTransportVaultPreflightError:
        os.close(current)
        raise
    except OSError as error:
        os.close(current)
        raise StaffTransportVaultPreflightError(
            f"{label} contains a symbolic-link or non-directory component"
        ) from error


def _pin_private_artifact(path: Path, *, label: str) -> _PinnedArtifact:
    absolute = _absolute_lexical(path)
    try:
        parent_descriptor = _open_directory_path_no_follow(
            absolute.parent,
            label=f"{label} parent",
        )
    except FileNotFoundError as error:
        raise StaffTransportVaultPreflightError(f"{label} parent is absent") from error
    descriptor = -1
    try:
        parent_details = os.fstat(parent_descriptor)
        expected_owner = os.geteuid() if hasattr(os, "geteuid") else parent_details.st_uid
        if (
            not stat.S_ISDIR(parent_details.st_mode)
            or _mode(parent_details) != 0o700
            or parent_details.st_uid != expected_owner
        ):
            raise StaffTransportVaultPreflightError(
                f"{label} parent must be an owned mode-0700 directory"
            )
        descriptor = os.open(
            absolute.name,
            _file_flags(),
            dir_fd=parent_descriptor,
        )
        opened = os.fstat(descriptor)
        listed = os.stat(
            absolute.name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISREG(opened.st_mode)
            or _mode(opened) != 0o600
            or opened.st_uid != expected_owner
            or opened.st_nlink != 1
            or _stable_stat(opened) != _stable_stat(listed)
        ):
            raise StaffTransportVaultPreflightError(
                f"{label} must remain an owned private single-link regular file"
            )
        return _PinnedArtifact(
            path=absolute,
            parent_descriptor=parent_descriptor,
            descriptor=descriptor,
            details=opened,
        )
    except OSError as error:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(parent_descriptor)
        raise StaffTransportVaultPreflightError(f"{label} could not be pinned safely") from error
    except BaseException:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(parent_descriptor)
        raise


def _read_pinned_bytes(
    artifact: _PinnedArtifact,
    *,
    maximum_bytes: int,
) -> bytes:
    before = os.fstat(artifact.descriptor)
    if _stable_stat(before) != _stable_stat(artifact.details):
        raise StaffTransportVaultPreflightError("Pinned backup artifact changed before read")
    os.lseek(artifact.descriptor, 0, os.SEEK_SET)
    content = bytearray()
    try:
        while True:
            chunk = os.read(artifact.descriptor, READ_CHUNK_BYTES)
            if not chunk:
                break
            content.extend(chunk)
            if len(content) > maximum_bytes:
                raise StaffTransportVaultPreflightError(
                    "Pinned backup artifact exceeds its read bound"
                )
        after = os.fstat(artifact.descriptor)
        if len(content) != before.st_size or _stable_stat(after) != _stable_stat(before):
            raise StaffTransportVaultPreflightError("Pinned backup artifact changed during read")
        return bytes(content)
    finally:
        content.clear()
        os.lseek(artifact.descriptor, 0, os.SEEK_SET)


def _hash_pinned_artifact(artifact: _PinnedArtifact) -> str:
    before = os.fstat(artifact.descriptor)
    if _stable_stat(before) != _stable_stat(artifact.details):
        raise StaffTransportVaultPreflightError("Pinned backup artifact changed before hashing")
    os.lseek(artifact.descriptor, 0, os.SEEK_SET)
    digest = hashlib.sha256()
    total = 0
    try:
        while True:
            chunk = os.read(artifact.descriptor, READ_CHUNK_BYTES)
            if not chunk:
                break
            total += len(chunk)
            digest.update(chunk)
        after = os.fstat(artifact.descriptor)
        if total != before.st_size or _stable_stat(after) != _stable_stat(before):
            raise StaffTransportVaultPreflightError("Pinned backup artifact changed during hashing")
        return digest.hexdigest()
    finally:
        os.lseek(artifact.descriptor, 0, os.SEEK_SET)


def _recheck_pinned_artifact(artifact: _PinnedArtifact, *, label: str) -> None:
    opened = os.fstat(artifact.descriptor)
    try:
        listed = os.stat(
            artifact.path.name,
            dir_fd=artifact.parent_descriptor,
            follow_symlinks=False,
        )
    except OSError as error:
        raise StaffTransportVaultPreflightError(f"{label} changed while pinned") from error
    if _stable_stat(opened) != _stable_stat(artifact.details) or _stable_stat(
        listed
    ) != _stable_stat(artifact.details):
        raise StaffTransportVaultPreflightError(f"{label} changed while pinned")
    try:
        current_parent = _open_directory_path_no_follow(
            artifact.path.parent,
            label=f"{label} current parent",
        )
    except FileNotFoundError as error:
        raise StaffTransportVaultPreflightError(f"{label} path changed while pinned") from error
    try:
        current = os.stat(
            artifact.path.name,
            dir_fd=current_parent,
            follow_symlinks=False,
        )
        if _stable_stat(current) != _stable_stat(artifact.details):
            raise StaffTransportVaultPreflightError(f"{label} path changed while pinned")
    except OSError as error:
        raise StaffTransportVaultPreflightError(f"{label} path changed while pinned") from error
    finally:
        os.close(current_parent)


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _decode_backup_value(value: Any) -> Any:
    if not isinstance(value, dict) or set(value) != {"$type", "value"}:
        return value
    kind = value["$type"]
    encoded = value["value"]
    if kind in {"uuid", "string", "decimal", "datetime", "date", "time"}:
        return str(encoded)
    if kind == "json":
        return encoded
    if kind == "bytes":
        raise StaffTransportVaultPreflightError(
            "Encrypted evidence inventory cannot contain encoded bytes"
        )
    raise StaffTransportVaultPreflightError(
        f"Unsupported encrypted evidence backup value type {kind!r}"
    )


def _decoded_row(payload: dict[str, Any]) -> dict[str, Any]:
    row = payload.get("row")
    if not isinstance(row, dict):
        raise StaffTransportVaultPreflightError("Encrypted evidence backup row is malformed")
    return {key: _decode_backup_value(value) for key, value in row.items()}


def _required_text(row: dict[str, Any], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value or value.strip() != value:
        raise StaffTransportVaultPreflightError(
            f"Encrypted evidence inventory field {key!r} is invalid"
        )
    return value


def _required_uuid(row: dict[str, Any], key: str) -> UUID:
    value = _required_text(row, key)
    try:
        return UUID(value)
    except ValueError as error:
        raise StaffTransportVaultPreflightError(
            f"Encrypted evidence inventory field {key!r} is not a UUID"
        ) from error


def _required_int(row: dict[str, Any], key: str) -> int:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise StaffTransportVaultPreflightError(
            f"Encrypted evidence inventory field {key!r} is invalid"
        )
    return value


def _canonical_reference_parts(reference: str) -> tuple[str, str, str, str]:
    path = PurePosixPath(reference)
    parts = path.parts
    if (
        path.is_absolute()
        or len(parts) != 4
        or reference != "/".join(parts)
        or any(CANONICAL_COMPONENT.fullmatch(part) is None for part in parts[:3])
        or parts[3] != "v1.enc"
        or "\\" in reference
        or "\x00" in reference
    ):
        raise StaffTransportVaultPreflightError(
            "Encrypted evidence storage reference is not a canonical v1.enc key"
        )
    return parts


def _metadata(row: dict[str, Any]) -> dict[str, Any]:
    media_type = _required_text(row, "media_type")
    byte_size = _required_int(row, "byte_size")
    content_sha256 = _required_text(row, "content_sha256")
    ciphertext_sha256 = _required_text(row, "ciphertext_sha256")
    encryption_key_id = _required_text(row, "encryption_key_id")
    if media_type not in {"application/pdf", "image/jpeg", "image/png"}:
        raise StaffTransportVaultPreflightError(
            "Encrypted evidence inventory media type is unsupported"
        )
    if not 1 <= byte_size <= MAXIMUM_PLAINTEXT_BYTES:
        raise StaffTransportVaultPreflightError(
            "Encrypted evidence inventory plaintext byte size is invalid"
        )
    if not LOWERCASE_SHA256.fullmatch(content_sha256) or not LOWERCASE_SHA256.fullmatch(
        ciphertext_sha256
    ):
        raise StaffTransportVaultPreflightError("Encrypted evidence inventory digest is invalid")
    if len(encryption_key_id) > 80:
        raise StaffTransportVaultPreflightError(
            "Encrypted evidence inventory key identifier is invalid"
        )
    return {
        "mediaType": media_type,
        "plaintextByteSize": byte_size,
        "ciphertextByteSize": byte_size + ENCRYPTED_CONTAINER_OVERHEAD_BYTES,
        "contentSha256": content_sha256,
        "ciphertextSha256": ciphertext_sha256,
        "encryptionKeyId": encryption_key_id,
    }


def _owner(table: str, row: dict[str, Any], parts: tuple[str, ...]) -> dict[str, Any]:
    row_id = _required_uuid(row, "id")
    storage_namespace_user_id = str(UUID(hex=parts[0]))
    storage_object_id = str(UUID(hex=parts[2]))
    if table == "staff_screening_document_versions":
        user_id = _required_uuid(row, "user_id")
        document_id = _required_uuid(row, "document_id")
        if parts[:3] != (user_id.hex, document_id.hex, row_id.hex):
            raise StaffTransportVaultPreflightError(
                "Staff screening storage reference does not match backup ownership"
            )
        return {
            "table": table,
            "rowId": str(row_id),
            "userId": str(user_id),
            "documentId": str(document_id),
            "versionNumber": _required_int(row, "version_number"),
            "storageNamespaceUserId": storage_namespace_user_id,
            "storageObjectId": storage_object_id,
        }
    if table == "staff_driver_qualification_evidence_objects":
        organization_id = _required_uuid(row, "organization_id")
        membership_id = _required_uuid(row, "membership_id")
        qualification_version_id = _required_uuid(row, "qualification_version_id")
        recorded_by_user_id = _required_uuid(row, "recorded_by_user_id")
        if parts[0] != recorded_by_user_id.hex or parts[1] != membership_id.hex:
            raise StaffTransportVaultPreflightError(
                "Driver qualification storage reference does not match backup ownership"
            )
        return {
            "table": table,
            "rowId": str(row_id),
            "organizationId": str(organization_id),
            "membershipId": str(membership_id),
            "qualificationVersionId": str(qualification_version_id),
            "recordedByUserId": str(recorded_by_user_id),
            "storageNamespaceUserId": storage_namespace_user_id,
            "storageObjectId": storage_object_id,
        }
    organization_id = _required_uuid(row, "organization_id")
    vehicle_id = _required_uuid(row, "vehicle_id")
    vehicle_version_id = _required_uuid(row, "vehicle_version_id")
    recorded_by_user_id = _required_uuid(row, "recorded_by_user_id")
    evidence_status = _required_text(row, "status")
    if evidence_status not in VEHICLE_EVIDENCE_STATUSES:
        raise StaffTransportVaultPreflightError(
            "Vehicle evidence relationship has an unsupported status"
        )
    if parts[1] != vehicle_id.hex:
        raise StaffTransportVaultPreflightError(
            "Vehicle evidence storage reference does not match backup ownership"
        )
    return {
        "table": table,
        "rowId": str(row_id),
        "organizationId": str(organization_id),
        "vehicleId": str(vehicle_id),
        "vehicleVersionId": str(vehicle_version_id),
        "evidenceType": _required_text(row, "evidence_type"),
        "versionNumber": _required_int(row, "version_number"),
        "status": evidence_status,
        "recordedByUserId": str(recorded_by_user_id),
        "storageNamespaceUserId": storage_namespace_user_id,
        "storageObjectId": storage_object_id,
    }


def _derive_inventory(
    backup_artifact: _PinnedArtifact,
    verified: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    tables = verified["header"].get("tables")
    if not isinstance(tables, list) or any(table not in tables for table in EVIDENCE_TABLES):
        raise StaffTransportVaultPreflightError(
            "Database backup does not contain all staff/transport evidence tables"
        )
    rows: list[tuple[str, dict[str, Any]]] = []
    os.lseek(backup_artifact.descriptor, 0, os.SEEK_SET)
    try:
        with (
            os.fdopen(os.dup(backup_artifact.descriptor), "rb", closefd=True) as raw,
            gzip.GzipFile(fileobj=raw, mode="rb") as compressed,
            io.TextIOWrapper(compressed, encoding="utf-8") as source,
        ):
            first = json.loads(next(source))
            if first.get("header") != verified["header"]:
                raise StaffTransportVaultPreflightError(
                    "Pinned backup header differs from the verified backup"
                )
            for line in source:
                payload = json.loads(line)
                table = payload.get("table")
                if table in EVIDENCE_TABLES:
                    rows.append((table, _decoded_row(payload)))
    except (OSError, EOFError, json.JSONDecodeError, StopIteration) as error:
        raise StaffTransportVaultPreflightError(
            "Unable to read encrypted evidence inventory from verified backup"
        ) from error
    finally:
        os.lseek(backup_artifact.descriptor, 0, os.SEEK_SET)

    expected_counts = {
        table: int(verified["tableCounts"].get(table, 0)) for table in EVIDENCE_TABLES
    }
    actual_counts = Counter(table for table, _row in rows)
    if any(actual_counts[table] != expected_counts[table] for table in EVIDENCE_TABLES):
        raise StaffTransportVaultPreflightError(
            "Encrypted evidence inventory does not match verified backup counts"
        )

    objects: dict[str, dict[str, Any]] = {}
    seen_rows: set[tuple[str, str]] = set()
    for table, row in rows:
        reference = _required_text(row, "storage_reference")
        parts = _canonical_reference_parts(reference)
        metadata = _metadata(row)
        ownership = _owner(table, row, parts)
        row_identity = (table, ownership["rowId"])
        if row_identity in seen_rows:
            raise StaffTransportVaultPreflightError(
                "Duplicate encrypted evidence row in database backup"
            )
        seen_rows.add(row_identity)
        existing = objects.get(reference)
        if existing is None:
            objects[reference] = {
                "storageReference": reference,
                **metadata,
                "ownershipRelationships": [ownership],
            }
            continue
        conflicting_fields = sorted(
            key for key, value in metadata.items() if existing[key] != value
        )
        if conflicting_fields:
            raise StaffTransportVaultPreflightError(
                "Shared encrypted evidence reference has conflicting metadata: "
                + ", ".join(conflicting_fields)
            )
        existing["ownershipRelationships"].append(ownership)

    inventory = sorted(objects.values(), key=lambda item: item["storageReference"])
    for item in inventory:
        item["ownershipRelationships"].sort(key=lambda value: (value["table"], value["rowId"]))
        relationships = item["ownershipRelationships"]
        tables = {value["table"] for value in relationships}
        if len(tables) != 1:
            raise StaffTransportVaultPreflightError(
                "Encrypted evidence reference is aliased across source tables"
            )
        if tables != {"transport_vehicle_evidence_versions"} and len(relationships) != 1:
            raise StaffTransportVaultPreflightError(
                "Non-vehicle encrypted evidence reference has multiple source rows"
            )
        if tables == {"transport_vehicle_evidence_versions"}:
            ownership = {
                (
                    value["organizationId"],
                    value["vehicleId"],
                    value["vehicleVersionId"],
                    value["evidenceType"],
                )
                for value in relationships
            }
            if len(ownership) != 1:
                raise StaffTransportVaultPreflightError(
                    "Shared vehicle evidence reference has conflicting ownership"
                )
            sources = [value for value in relationships if value["status"] == "provided"]
            if (
                len(sources) != 1
                or sources[0]["recordedByUserId"] != sources[0]["storageNamespaceUserId"]
            ):
                raise StaffTransportVaultPreflightError(
                    "Shared vehicle evidence reference lacks one namespace-bound source"
                )
    return inventory, expected_counts


def _enumerate_vault(
    root_descriptor: int,
    root_details: os.stat_result,
) -> tuple[
    dict[str, _NodeRecord],
    dict[str, _NodeRecord],
    list[dict[str, str]],
    list[dict[str, str]],
]:
    files: dict[str, _NodeRecord] = {}
    directories: dict[str, _NodeRecord] = {}
    unsafe: list[dict[str, str]] = []
    indeterminate: list[dict[str, str]] = []
    expected_owner = os.geteuid() if hasattr(os, "geteuid") else root_details.st_uid

    def walk(
        descriptor: int,
        relative: PurePosixPath,
        opened_details: os.stat_result,
    ) -> None:
        try:
            with os.scandir(descriptor) as iterator:
                entries = sorted(iterator, key=lambda entry: entry.name)
        except OSError:
            indeterminate.append(
                {"reference": relative.as_posix(), "reason": "directory_unreadable"}
            )
            return
        for entry in entries:
            child_relative = relative / entry.name
            reference = child_relative.as_posix()
            try:
                details = entry.stat(follow_symlinks=False)
            except OSError:
                indeterminate.append({"reference": reference, "reason": "entry_unreadable"})
                continue
            if stat.S_ISLNK(details.st_mode):
                unsafe.append({"reference": reference, "reason": "symbolic_link"})
                continue
            if stat.S_ISDIR(details.st_mode):
                record = _node_record(reference, details)
                directories[reference] = record
                if len(child_relative.parts) > 3:
                    unsafe.append({"reference": reference, "reason": "directory_depth_exceeded"})
                    continue
                if _mode(details) != 0o700:
                    unsafe.append({"reference": reference, "reason": "directory_mode_not_0700"})
                    continue
                if details.st_uid != expected_owner:
                    unsafe.append({"reference": reference, "reason": "directory_owner_mismatch"})
                    continue
                if details.st_dev != root_details.st_dev:
                    unsafe.append({"reference": reference, "reason": "cross_device_directory"})
                    continue
                try:
                    child_descriptor = os.open(
                        entry.name,
                        _directory_flags(),
                        dir_fd=descriptor,
                    )
                except OSError:
                    indeterminate.append(
                        {"reference": reference, "reason": "directory_changed_before_open"}
                    )
                    continue
                try:
                    opened_child = os.fstat(child_descriptor)
                    if _stable_stat(opened_child) != _stable_stat(details):
                        indeterminate.append(
                            {
                                "reference": reference,
                                "reason": "directory_changed_before_open",
                            }
                        )
                        continue
                    walk(child_descriptor, child_relative, opened_child)
                finally:
                    os.close(child_descriptor)
                continue
            if stat.S_ISREG(details.st_mode):
                files[reference] = _node_record(reference, details)
                if _mode(details) != 0o600:
                    unsafe.append({"reference": reference, "reason": "file_mode_not_0600"})
                if details.st_uid != expected_owner:
                    unsafe.append({"reference": reference, "reason": "file_owner_mismatch"})
                if details.st_nlink != 1:
                    unsafe.append({"reference": reference, "reason": "file_link_count_not_one"})
                continue
            unsafe.append({"reference": reference, "reason": "special_file"})
        try:
            after = os.fstat(descriptor)
        except OSError:
            indeterminate.append(
                {
                    "reference": relative.as_posix(),
                    "reason": "directory_became_unreadable",
                }
            )
            return
        if _stable_stat(after) != _stable_stat(opened_details):
            indeterminate.append(
                {
                    "reference": relative.as_posix(),
                    "reason": "directory_changed_during_scan",
                }
            )

    walk(root_descriptor, PurePosixPath(), root_details)
    return files, directories, unsafe, indeterminate


def _measurement(record: _NodeRecord, digest: str | None) -> dict[str, Any]:
    return {
        "device": record.device,
        "inode": record.inode,
        "mode": f"{record.mode:04o}",
        "ownerUid": record.owner,
        "linkCount": record.links,
        "byteSize": record.size,
        "modifiedNs": record.modified_ns,
        "changedNs": record.changed_ns,
        "ciphertextSha256": digest,
    }


def _measure_file(
    root_descriptor: int,
    root_details: os.stat_result,
    reference: str,
    *,
    file_record: _NodeRecord,
    directory_records: dict[str, _NodeRecord],
    maximum_bytes: int,
    include_digest: bool,
) -> dict[str, Any]:
    parts = PurePosixPath(reference).parts
    descriptors: list[tuple[int, os.stat_result]] = []
    file_descriptor: int | None = None
    current = root_descriptor
    expected_owner = os.geteuid() if hasattr(os, "geteuid") else root_details.st_uid
    try:
        root_before = os.fstat(root_descriptor)
        if _stable_stat(root_before) != _stable_stat(root_details):
            raise _MeasurementIssue("vault_changed_after_scan", indeterminate=True)
        for index, part in enumerate(parts[:-1], start=1):
            prefix = "/".join(parts[:index])
            expected = directory_records.get(prefix)
            if expected is None:
                raise _MeasurementIssue("directory_changed_after_scan", indeterminate=True)
            try:
                child = os.open(part, _directory_flags(), dir_fd=current)
            except OSError as error:
                raise _MeasurementIssue(
                    "directory_changed_after_scan", indeterminate=True
                ) from error
            details = os.fstat(child)
            if (
                not _record_matches(expected, details)
                or not stat.S_ISDIR(details.st_mode)
                or _mode(details) != 0o700
                or details.st_uid != expected_owner
                or details.st_dev != root_details.st_dev
            ):
                os.close(child)
                raise _MeasurementIssue("directory_changed_after_scan", indeterminate=True)
            descriptors.append((child, details))
            current = child
        try:
            file_descriptor = os.open(parts[-1], _file_flags(), dir_fd=current)
        except OSError as error:
            raise _MeasurementIssue("file_changed_after_scan", indeterminate=True) from error
        before = os.fstat(file_descriptor)
        if not _record_matches(file_record, before):
            raise _MeasurementIssue("file_changed_after_scan", indeterminate=True)
        if (
            not stat.S_ISREG(before.st_mode)
            or _mode(before) != 0o600
            or before.st_uid != expected_owner
            or before.st_nlink != 1
            or before.st_dev != root_details.st_dev
        ):
            raise _MeasurementIssue("unsafe_leaf", indeterminate=False)
        if include_digest and before.st_size > maximum_bytes:
            raise _MeasurementIssue("measurement_limit_exceeded", indeterminate=True)

        digest = hashlib.sha256() if include_digest else None
        total = 0
        if digest is not None:
            while True:
                chunk = os.read(file_descriptor, READ_CHUNK_BYTES)
                if not chunk:
                    break
                total += len(chunk)
                if total > maximum_bytes:
                    if _stable_stat(os.fstat(file_descriptor)) != _stable_stat(before):
                        raise _MeasurementIssue("concurrent_file_change", indeterminate=True)
                    raise _MeasurementIssue("measurement_limit_exceeded", indeterminate=True)
                digest.update(chunk)
        after = os.fstat(file_descriptor)
        if (digest is not None and total != before.st_size) or _stable_stat(after) != _stable_stat(
            before
        ):
            raise _MeasurementIssue("concurrent_file_change", indeterminate=True)
        for descriptor, opened in descriptors:
            if _stable_stat(os.fstat(descriptor)) != _stable_stat(opened):
                raise _MeasurementIssue("concurrent_directory_change", indeterminate=True)
        if _stable_stat(os.fstat(root_descriptor)) != _stable_stat(root_before):
            raise _MeasurementIssue("concurrent_vault_change", indeterminate=True)
        return _measurement(
            file_record,
            digest.hexdigest() if digest is not None else None,
        )
    except OSError as error:
        raise _MeasurementIssue("measurement_io_error", indeterminate=True) from error
    finally:
        if file_descriptor is not None:
            os.close(file_descriptor)
        for descriptor, _details in reversed(descriptors):
            os.close(descriptor)


def _deduplicate_findings(values: list[dict[str, str]]) -> list[dict[str, str]]:
    unique = {(value["reference"], value["reason"]) for value in values}
    return [{"reference": reference, "reason": reason} for reference, reason in sorted(unique)]


def _prefixes(reference: str) -> set[str]:
    parts = PurePosixPath(reference).parts
    return {"/".join(parts[:index]) for index in range(1, len(parts))}


def _is_canonical_reference(reference: str) -> bool:
    try:
        _canonical_reference_parts(reference)
    except StaffTransportVaultPreflightError:
        return False
    return True


def _absent_analysis(inventory: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "expectedCount": len(inventory),
        "presentCount": 0,
        "missing": sorted(item["storageReference"] for item in inventory),
        "mismatch": [],
        "unsafe": [{"reference": ".", "reason": "vault_root_absent"}],
        "unexpected": [],
        "indeterminate": [],
        "vaultIdentity": None,
    }


def _analyze_vault(
    inventory: list[dict[str, Any]],
    vault_root: Path,
) -> dict[str, Any]:
    expected = {item["storageReference"]: item for item in inventory}
    root = _absolute_lexical(vault_root)
    try:
        root_descriptor = _open_directory_path_no_follow(root, label="Staff vault root")
    except FileNotFoundError:
        return _absent_analysis(inventory)
    try:
        root_details = os.fstat(root_descriptor)
        expected_owner = os.geteuid() if hasattr(os, "geteuid") else root_details.st_uid
        root_unsafe: list[dict[str, str]] = []
        if not stat.S_ISDIR(root_details.st_mode):
            root_unsafe.append({"reference": ".", "reason": "vault_root_not_directory"})
        if _mode(root_details) != 0o700:
            root_unsafe.append({"reference": ".", "reason": "vault_root_mode_not_0700"})
        if root_details.st_uid != expected_owner:
            root_unsafe.append({"reference": ".", "reason": "vault_root_owner_mismatch"})
        if root_unsafe:
            result = _absent_analysis(inventory)
            result["unsafe"] = root_unsafe
            result["vaultIdentity"] = {
                "device": root_details.st_dev,
                "inode": root_details.st_ino,
                "mode": f"{_mode(root_details):04o}",
                "ownerUid": root_details.st_uid,
            }
            return result

        files, directories, unsafe, indeterminate = _enumerate_vault(
            root_descriptor,
            root_details,
        )
        missing: list[str] = []
        mismatch: list[dict[str, str]] = []
        present: list[str] = []
        for reference, item in sorted(expected.items()):
            record = files.get(reference)
            if record is None:
                missing.append(reference)
                continue
            size_mismatch = record.size != item["ciphertextByteSize"]
            try:
                measured = _measure_file(
                    root_descriptor,
                    root_details,
                    reference,
                    file_record=record,
                    directory_records=directories,
                    maximum_bytes=item["ciphertextByteSize"],
                    include_digest=not size_mismatch,
                )
            except _MeasurementIssue as error:
                target = indeterminate if error.indeterminate else mismatch
                target.append({"reference": reference, "reason": error.reason})
                continue
            if size_mismatch or measured["byteSize"] != item["ciphertextByteSize"]:
                mismatch.append({"reference": reference, "reason": "ciphertext_byte_size_mismatch"})
            elif measured["ciphertextSha256"] != item["ciphertextSha256"]:
                mismatch.append({"reference": reference, "reason": "ciphertext_sha256_mismatch"})
            else:
                present.append(reference)

        unexpected: list[dict[str, Any]] = []
        expected_prefixes = (
            set().union(*(_prefixes(reference) for reference in expected)) if expected else set()
        )
        for reference, record in sorted(files.items()):
            if reference in expected:
                continue
            reasons = [] if _is_canonical_reference(reference) else ["noncanonical_reference"]
            measured: dict[str, Any] | None = None
            try:
                measured = _measure_file(
                    root_descriptor,
                    root_details,
                    reference,
                    file_record=record,
                    directory_records=directories,
                    maximum_bytes=MAXIMUM_CIPHERTEXT_BYTES,
                    include_digest=True,
                )
            except _MeasurementIssue as error:
                reasons.append(error.reason)
                if error.indeterminate:
                    indeterminate.append({"reference": reference, "reason": error.reason})
            unexpected.append(
                {
                    "reference": reference,
                    "kind": "file",
                    "canonical": _is_canonical_reference(reference),
                    "reasons": sorted(set(reasons)),
                    "measurement": measured,
                }
            )
        for reference, record in sorted(directories.items()):
            if reference not in expected_prefixes:
                unexpected.append(
                    {
                        "reference": reference,
                        "kind": "directory",
                        "canonical": False,
                        "reasons": ["not_in_backup_inventory"],
                        "measurement": _measurement(record, None),
                    }
                )

        try:
            reopened = _open_directory_path_no_follow(root, label="Staff vault root")
        except (FileNotFoundError, StaffTransportVaultPreflightError):
            indeterminate.append({"reference": ".", "reason": "vault_root_path_changed"})
        else:
            try:
                reopened_details = os.fstat(reopened)
                if (reopened_details.st_dev, reopened_details.st_ino) != (
                    root_details.st_dev,
                    root_details.st_ino,
                ):
                    indeterminate.append({"reference": ".", "reason": "vault_root_path_changed"})
            finally:
                os.close(reopened)

        return {
            "expectedCount": len(expected),
            "presentCount": len(present),
            "missing": sorted(missing),
            "mismatch": _deduplicate_findings(mismatch),
            "unsafe": _deduplicate_findings(unsafe),
            "unexpected": sorted(
                unexpected,
                key=lambda item: (item["reference"], item["kind"]),
            ),
            "indeterminate": _deduplicate_findings(indeterminate),
            "vaultIdentity": {
                "device": root_details.st_dev,
                "inode": root_details.st_ino,
                "mode": f"{_mode(root_details):04o}",
                "ownerUid": root_details.st_uid,
                "modifiedNs": root_details.st_mtime_ns,
                "changedNs": root_details.st_ctime_ns,
            },
        }
    finally:
        os.close(root_descriptor)


def _normalize_now(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None or value.utcoffset() is None:
        raise StaffTransportVaultPreflightError("Preflight time must include a timezone")
    return value.astimezone(UTC)


def _verify_artifacts(backup_path: Path, manifest_path: Path) -> dict[str, Any]:
    try:
        return verify_backup_artifacts(backup_path, manifest_path)
    except BackupContractError as error:
        raise StaffTransportVaultPreflightError(str(error)) from error


def _inventory_projection(
    *,
    backup_path: Path,
    manifest_path: Path,
    manifest_sha256: str,
    verified: dict[str, Any],
    inventory: list[dict[str, Any]],
    source_row_counts: dict[str, int],
) -> dict[str, Any]:
    key_object_counts = Counter(item["encryptionKeyId"] for item in inventory)
    key_relationship_counts: Counter[str] = Counter()
    for item in inventory:
        key_relationship_counts[item["encryptionKeyId"]] += len(item["ownershipRelationships"])
    key_id_counts = [
        {
            "encryptionKeyId": key_id,
            "uniqueObjectCount": key_object_counts[key_id],
            "ownershipRelationshipCount": key_relationship_counts[key_id],
        }
        for key_id in sorted(key_object_counts)
    ]
    relationship_count = sum(len(item["ownershipRelationships"]) for item in inventory)
    return {
        "databaseBackup": {
            "backup": backup_path.name,
            "manifest": manifest_path.name,
            "sha256Compressed": verified["manifest"]["sha256Compressed"],
            "sha256Manifest": manifest_sha256,
            "sha256Rows": verified["manifest"]["sha256Rows"],
            "alembicRevisions": verified["header"].get(
                "alembicRevisions",
                [],
            ),
        },
        "inventory": {
            "sha256": hashlib.sha256(_canonical_json(inventory)).hexdigest(),
            "uniqueObjectCount": len(inventory),
            "ownershipRelationshipCount": relationship_count,
            "sourceRowCounts": source_row_counts,
            "keyIdCounts": key_id_counts,
            "objects": inventory,
        },
    }


@contextmanager
def pinned_staff_transport_inventory(
    backup_path: Path,
    manifest_path: Path,
):
    """Yield one backup-derived inventory while both artifacts remain pinned.

    The context rechecks pathname identity and the complete logical-backup
    contract after the caller's bounded work. Callers may therefore copy or
    measure vault bytes without weakening the preflight's swap-race defenses.
    """

    verified = _verify_artifacts(backup_path, manifest_path)
    backup_artifact = _pin_private_artifact(backup_path, label="Database backup")
    try:
        manifest_artifact = _pin_private_artifact(
            manifest_path,
            label="Database backup manifest",
        )
        try:
            manifest_content = _read_pinned_bytes(
                manifest_artifact,
                maximum_bytes=MAXIMUM_MANIFEST_BYTES,
            )
            try:
                pinned_manifest = json.loads(manifest_content)
            except json.JSONDecodeError as error:
                raise StaffTransportVaultPreflightError(
                    "Pinned database backup manifest is invalid"
                ) from error
            if pinned_manifest != verified["manifest"]:
                raise StaffTransportVaultPreflightError(
                    "Pinned database backup manifest differs from verified content"
                )
            manifest_sha256 = hashlib.sha256(manifest_content).hexdigest()
            if _hash_pinned_artifact(backup_artifact) != pinned_manifest["sha256Compressed"]:
                raise StaffTransportVaultPreflightError(
                    "Pinned database backup differs from its verified manifest"
                )

            inventory, source_row_counts = _derive_inventory(
                backup_artifact,
                verified,
            )
            projection = _inventory_projection(
                backup_path=backup_path,
                manifest_path=manifest_path,
                manifest_sha256=manifest_sha256,
                verified=verified,
                inventory=inventory,
                source_row_counts=source_row_counts,
            )
            _recheck_pinned_artifact(backup_artifact, label="Database backup")
            _recheck_pinned_artifact(
                manifest_artifact,
                label="Database backup manifest",
            )
            yield projection
            _recheck_pinned_artifact(backup_artifact, label="Database backup")
            _recheck_pinned_artifact(
                manifest_artifact,
                label="Database backup manifest",
            )
            verified_after = _verify_artifacts(backup_path, manifest_path)
            if verified_after != verified:
                raise StaffTransportVaultPreflightError(
                    "Verified database backup artifacts changed during inventory use"
                )
            _recheck_pinned_artifact(backup_artifact, label="Database backup")
            _recheck_pinned_artifact(
                manifest_artifact,
                label="Database backup manifest",
            )
        finally:
            manifest_artifact.close()
    finally:
        backup_artifact.close()


def derive_staff_transport_inventory(
    backup_path: Path,
    manifest_path: Path,
) -> dict[str, Any]:
    """Return the exact encrypted-object inventory from a verified backup."""

    with pinned_staff_transport_inventory(backup_path, manifest_path) as projection:
        return projection


def preflight_staff_transport_vault(
    backup_path: Path,
    manifest_path: Path,
    vault_root: Path,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Derive and measure one backup-bound, report-only encrypted inventory."""

    generated_at = _normalize_now(now)
    with pinned_staff_transport_inventory(backup_path, manifest_path) as projection:
        inventory = projection["inventory"]["objects"]
        analysis = _analyze_vault(inventory, vault_root)
        return {
            "format": PREFLIGHT_FORMAT,
            "mode": "report_only",
            "generatedAt": generated_at.isoformat(),
            "databaseBackup": projection["databaseBackup"],
            "vaultRoot": os.fspath(_absolute_lexical(vault_root)),
            "inventory": projection["inventory"],
            **analysis,
            "consistencyAuthority": False,
            "purgeAuthority": False,
            "blocker": BLOCKER,
        }


def write_preflight_receipt(path: Path, payload: dict[str, Any]) -> None:
    """Write one durable mode-0600 receipt without replacing any path."""

    absolute = _absolute_lexical(path)
    vault_root_value = payload.get("vaultRoot")
    if not isinstance(vault_root_value, str):
        raise StaffTransportVaultPreflightError("Preflight receipt has no vault binding")
    vault_root = _absolute_lexical(Path(vault_root_value))
    if absolute == vault_root or vault_root in absolute.parents:
        raise StaffTransportVaultPreflightError(
            "Preflight receipt cannot be written inside the evidence vault"
        )
    if absolute.name in {"", ".", ".."}:
        raise StaffTransportVaultPreflightError("Preflight receipt path is invalid")
    vault_identity_value = payload.get("vaultIdentity")
    forbidden_identity: tuple[int, int] | None = None
    if vault_identity_value is not None:
        if (
            not isinstance(vault_identity_value, dict)
            or isinstance(vault_identity_value.get("device"), bool)
            or not isinstance(vault_identity_value.get("device"), int)
            or isinstance(vault_identity_value.get("inode"), bool)
            or not isinstance(vault_identity_value.get("inode"), int)
        ):
            raise StaffTransportVaultPreflightError(
                "Preflight receipt has an invalid vault identity"
            )
        forbidden_identity = (
            vault_identity_value["device"],
            vault_identity_value["inode"],
        )
    serialized = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    try:
        parent_descriptor = _open_directory_path_no_follow(
            absolute.parent,
            label="Preflight receipt parent",
            forbidden_identity=forbidden_identity,
        )
    except FileNotFoundError as error:
        raise StaffTransportVaultPreflightError("Preflight receipt parent is absent") from error
    try:
        parent_details = os.fstat(parent_descriptor)
        expected_owner = os.geteuid() if hasattr(os, "geteuid") else parent_details.st_uid
        if (
            not stat.S_ISDIR(parent_details.st_mode)
            or _mode(parent_details) != 0o700
            or parent_details.st_uid != expected_owner
        ):
            raise StaffTransportVaultPreflightError(
                "Preflight receipt parent must be an owned mode-0700 directory"
            )
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        try:
            descriptor = os.open(
                absolute.name,
                flags,
                0o600,
                dir_fd=parent_descriptor,
            )
        except FileExistsError as error:
            raise StaffTransportVaultPreflightError(
                f"Refusing to replace existing preflight receipt {absolute}"
            ) from error
        except OSError as error:
            raise StaffTransportVaultPreflightError(
                "Preflight receipt could not be created safely"
            ) from error
        try:
            os.fchmod(descriptor, 0o600)
            remaining = memoryview(serialized)
            while remaining:
                written = os.write(descriptor, remaining)
                if written < 1:
                    raise OSError("Preflight receipt write made no progress")
                remaining = remaining[written:]
            os.fsync(descriptor)
            opened = os.fstat(descriptor)
            listed = os.stat(
                absolute.name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
            if (
                not stat.S_ISREG(opened.st_mode)
                or (opened.st_dev, opened.st_ino) != (listed.st_dev, listed.st_ino)
                or _mode(opened) != 0o600
                or opened.st_uid != expected_owner
                or opened.st_nlink != 1
                or opened.st_size != len(serialized)
            ):
                raise StaffTransportVaultPreflightError(
                    "Preflight receipt did not remain a private single-link file"
                )
        except OSError as error:
            raise StaffTransportVaultPreflightError(
                "Preflight receipt could not be written durably"
            ) from error
        finally:
            # A failed write leaves its no-clobber artifact in place for inspection.
            os.close(descriptor)
        os.fsync(parent_descriptor)
    finally:
        os.close(parent_descriptor)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--vault-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        receipt = preflight_staff_transport_vault(
            args.backup,
            args.manifest,
            args.vault_root,
        )
        write_preflight_receipt(args.output, receipt)
        print(f"Preflight receipt written: {_absolute_lexical(args.output)}")
    except StaffTransportVaultPreflightError as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
