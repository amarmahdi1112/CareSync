"""Create, verify, and no-clobber restore a private family-evidence bundle.

The database backup remains the source of truth.  This tool first verifies the
logical backup and then derives the exact evidence-object inventory from that
snapshot.  It never queries a live database and never trusts a caller-supplied
object list.

Every persisted object row requires byte-identical private content, including
objects whose terminal assessment rejected them as malware.  Rejection makes
an object unusable; it is not an implicit deletion or purge lifecycle.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import shutil
import stat
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO
from uuid import UUID, uuid4

from scripts.backup_database import (
    BackupContractError,
    _require_private_mode,
    _sha256_file,
    verify_backup_artifacts,
)

EVIDENCE_BUNDLE_FORMAT = "caresync-family-evidence-vault-bundle-v1"
EVIDENCE_RESTORE_RECEIPT_FORMAT = "caresync-family-evidence-vault-restore-v1"
OBJECT_TABLE = "family_authority_evidence_objects"
ASSESSMENT_TABLE = "family_authority_evidence_object_assessments"
INCLUDED_DISPOSITION = "included"
READ_CHUNK_BYTES = 1024 * 1024
LOWERCASE_SHA256 = re.compile(r"^[0-9a-f]{64}$")
MEDIA_SUFFIXES = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
}
DOCUMENT_EVIDENCE_KINDS = {
    "identity_document",
    "custody_document",
    "court_order",
    "signed_consent",
    "signed_release_delegation",
    "other_document",
}
MAX_OBJECT_BYTES = 50 * 1024 * 1024
DEFAULT_VAULT_ROOT = (
    Path.home()
    / "Library"
    / "Application Support"
    / "CareSync Basic"
    / "private-family-authority-vault"
)


class EvidenceVaultBundleError(RuntimeError):
    """Raised when database metadata and private evidence bytes do not agree."""


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _inventory_digest(objects: list[dict[str, Any]]) -> str:
    return hashlib.sha256(_canonical_json(objects)).hexdigest()


def _decode_backup_value(value: Any) -> Any:
    if not isinstance(value, dict) or set(value) != {"$type", "value"}:
        return value
    kind = value["$type"]
    encoded = value["value"]
    if kind in {"uuid", "string"}:
        return str(encoded)
    if kind == "decimal":
        return str(encoded)
    if kind in {"datetime", "date", "time"}:
        return str(encoded)
    if kind == "json":
        return encoded
    if kind == "bytes":
        raise EvidenceVaultBundleError("Evidence inventory cannot contain encoded bytes")
    raise EvidenceVaultBundleError(f"Unsupported backup value type {kind!r}")


def _decoded_row(payload: dict[str, Any]) -> dict[str, Any]:
    row = payload.get("row")
    if not isinstance(row, dict):
        raise EvidenceVaultBundleError("Evidence backup row is malformed")
    return {key: _decode_backup_value(value) for key, value in row.items()}


def _required_text(row: dict[str, Any], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value:
        raise EvidenceVaultBundleError(f"Evidence inventory field {key!r} is invalid")
    return value


def _required_uuid(row: dict[str, Any], key: str) -> str:
    value = _required_text(row, key)
    try:
        return str(UUID(value))
    except ValueError as error:
        raise EvidenceVaultBundleError(f"Evidence inventory field {key!r} is not a UUID") from error


def _required_int(row: dict[str, Any], key: str) -> int:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise EvidenceVaultBundleError(f"Evidence inventory field {key!r} is invalid")
    return value


def _validate_storage_reference(
    reference: str,
    *,
    organization_id: str,
    family_id: str,
    object_id: str,
    media_type: str,
) -> None:
    path = PurePosixPath(reference)
    parts = path.parts
    expected = (
        UUID(organization_id).hex,
        UUID(family_id).hex,
        UUID(object_id).hex,
        f"v1{MEDIA_SUFFIXES[media_type]}",
    )
    if (
        reference != "/".join(expected)
        or path.is_absolute()
        or parts != expected
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise EvidenceVaultBundleError("Evidence storage reference is not an opaque v1 key")
    if "\\" in reference or "\x00" in reference:
        raise EvidenceVaultBundleError("Evidence storage reference contains an unsafe separator")


def derive_evidence_inventory_from_rows(
    object_rows: list[dict[str, Any]],
    assessment_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Canonicalize evidence rows obtained from an independently restored database."""

    objects_by_id: dict[str, dict[str, Any]] = {}
    assessments_by_object: dict[str, list[dict[str, Any]]] = {}
    for source_row in object_rows:
        row = dict(source_row)
        object_id = _required_uuid(row, "id")
        if object_id in objects_by_id:
            raise EvidenceVaultBundleError("Duplicate evidence object in database rows")
        objects_by_id[object_id] = row
    for source_row in assessment_rows:
        row = dict(source_row)
        object_id = _required_uuid(row, "evidence_object_id")
        assessments_by_object.setdefault(object_id, []).append(row)

    unknown_assessments = set(assessments_by_object) - set(objects_by_id)
    if unknown_assessments:
        raise EvidenceVaultBundleError("Evidence assessment references an absent object")

    inventory: list[dict[str, Any]] = []
    for object_id, row in sorted(objects_by_id.items()):
        organization_id = _required_uuid(row, "organization_id")
        family_id = _required_uuid(row, "family_id")
        evidence_kind = _required_text(row, "evidence_kind")
        object_version = _required_int(row, "object_version")
        storage_reference = _required_text(row, "storage_reference")
        media_type = _required_text(row, "media_type")
        byte_size = _required_int(row, "byte_size")
        content_sha256 = _required_text(row, "content_sha256")
        object_status = _required_text(row, "status")
        if object_version != 1:
            raise EvidenceVaultBundleError(
                "Evidence bundle supports only immutable object version 1"
            )
        if evidence_kind not in DOCUMENT_EVIDENCE_KINDS:
            raise EvidenceVaultBundleError("Evidence object has an unsupported document kind")
        if media_type not in MEDIA_SUFFIXES:
            raise EvidenceVaultBundleError("Evidence object has an unsupported media type")
        if (
            byte_size < 1
            or byte_size > MAX_OBJECT_BYTES
            or not LOWERCASE_SHA256.fullmatch(content_sha256)
        ):
            raise EvidenceVaultBundleError("Evidence object measurements are invalid")
        if object_status not in {"quarantined", "clean", "rejected"}:
            raise EvidenceVaultBundleError("Evidence object has an unsupported lifecycle state")
        _validate_storage_reference(
            storage_reference,
            organization_id=organization_id,
            family_id=family_id,
            object_id=object_id,
            media_type=media_type,
        )

        assessments = assessments_by_object.get(object_id, [])
        normalized_assessments: list[tuple[int, str, str | None]] = []
        for assessment in assessments:
            if (
                _required_uuid(assessment, "organization_id") != organization_id
                or _required_uuid(assessment, "family_id") != family_id
            ):
                raise EvidenceVaultBundleError("Evidence assessment escaped its tenant or family")
            version = _required_int(assessment, "version_number")
            decision = _required_text(assessment, "decision")
            reason = assessment.get("reason_code")
            if reason is not None and not isinstance(reason, str):
                raise EvidenceVaultBundleError("Evidence assessment reason is malformed")
            normalized_assessments.append((version, decision, reason))
        normalized_assessments.sort()

        if object_status == "quarantined":
            expected_assessments = [(1, "quarantined", None)]
        elif object_status == "clean":
            expected_assessments = [(1, "quarantined", None), (2, "clean", None)]
        else:
            if len(normalized_assessments) != 2:
                raise EvidenceVaultBundleError("Rejected evidence object lacks terminal provenance")
            terminal_reason = normalized_assessments[-1][2]
            if terminal_reason not in {"malware_detected", "invalid_document"}:
                raise EvidenceVaultBundleError(
                    "Rejected evidence object has an unknown policy reason"
                )
            expected_assessments = [
                (1, "quarantined", None),
                (2, "rejected", terminal_reason),
            ]
        if normalized_assessments != expected_assessments:
            raise EvidenceVaultBundleError("Evidence object assessment history is inconsistent")

        terminal_version, terminal_decision, terminal_reason = normalized_assessments[-1]
        inventory.append(
            {
                "objectId": object_id,
                "organizationId": organization_id,
                "familyId": family_id,
                "evidenceKind": evidence_kind,
                "objectVersion": object_version,
                "storageReference": storage_reference,
                "mediaType": media_type,
                "byteSize": byte_size,
                "contentSha256": content_sha256,
                "lifecycleStatus": object_status,
                "assessmentVersion": terminal_version,
                "assessmentDecision": terminal_decision,
                "terminalReasonCode": terminal_reason,
                "disposition": INCLUDED_DISPOSITION,
            }
        )
    return inventory


def _derive_inventory(
    backup_path: Path,
    verified_backup: dict[str, Any],
) -> list[dict[str, Any]]:
    tables = verified_backup["header"].get("tables")
    if not isinstance(tables, list) or OBJECT_TABLE not in tables or ASSESSMENT_TABLE not in tables:
        raise EvidenceVaultBundleError(
            "Database backup does not contain the 0029A1 evidence-vault tables"
        )

    object_rows: list[dict[str, Any]] = []
    assessment_rows: list[dict[str, Any]] = []
    try:
        with gzip.open(backup_path, "rt", encoding="utf-8") as source:
            next(source)
            for line in source:
                payload = json.loads(line)
                table = payload.get("table")
                if table == OBJECT_TABLE:
                    object_rows.append(_decoded_row(payload))
                elif table == ASSESSMENT_TABLE:
                    assessment_rows.append(_decoded_row(payload))
    except (OSError, EOFError, json.JSONDecodeError, StopIteration) as error:
        raise EvidenceVaultBundleError("Unable to read evidence inventory from backup") from error
    return derive_evidence_inventory_from_rows(object_rows, assessment_rows)


def derive_evidence_inventory(
    backup_path: Path,
    manifest_path: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Verify the logical backup and derive its exact evidence-object inventory."""

    try:
        verified = verify_backup_artifacts(backup_path, manifest_path)
    except BackupContractError as error:
        raise EvidenceVaultBundleError(str(error)) from error
    return verified, _derive_inventory(backup_path, verified)


def _assert_no_symlink_components(path: Path) -> None:
    absolute = Path(os.path.abspath(path.expanduser()))
    cursor = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        cursor = cursor / part
        if os.path.lexists(cursor) and stat.S_ISLNK(cursor.lstat().st_mode):
            raise EvidenceVaultBundleError(f"Private path {path} contains a symbolic link")


def _canonical_operation_path(path: Path, *, label: str) -> Path:
    raw = Path(path)
    if not raw.is_absolute():
        raise EvidenceVaultBundleError(f"{label} must be an absolute path")
    if any(part in {".", ".."} or part.startswith("~") for part in raw.parts):
        raise EvidenceVaultBundleError(
            f"{label} cannot contain dot traversal or home-expansion components"
        )
    absolute = Path(os.path.abspath(os.fspath(raw)))
    _assert_no_symlink_components(absolute)
    return absolute


def _open_directory_no_follow(path: Path) -> int:
    absolute = Path(os.path.abspath(path))
    if not hasattr(os, "O_DIRECTORY") or not hasattr(os, "O_NOFOLLOW"):
        raise EvidenceVaultBundleError("This platform cannot safely manage bundle artifacts")
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
        raise EvidenceVaultBundleError(
            "Private artifact directory contains an unsafe component"
        ) from error


def _unlink_if_identity(path: Path, identity: tuple[int, int] | None) -> None:
    if identity is None:
        return
    try:
        parent_descriptor = _open_directory_no_follow(path.parent)
    except EvidenceVaultBundleError:
        return
    try:
        try:
            details = os.stat(path.name, dir_fd=parent_descriptor, follow_symlinks=False)
        except OSError:
            return
        if (details.st_dev, details.st_ino) != identity:
            return
        try:
            os.unlink(path.name, dir_fd=parent_descriptor)
            os.fsync(parent_descriptor)
        except OSError:
            return
    finally:
        os.close(parent_descriptor)


def _ensure_private_directory(path: Path) -> None:
    _assert_no_symlink_components(path)
    if os.path.lexists(path):
        if path.is_symlink() or not path.is_dir():
            raise EvidenceVaultBundleError(f"Private path {path} is not a safe directory")
    else:
        missing: list[Path] = []
        cursor = path
        while not os.path.lexists(cursor):
            missing.append(cursor)
            parent = cursor.parent
            if parent == cursor:
                raise EvidenceVaultBundleError("Private directory has no existing ancestor")
            cursor = parent
        if cursor.is_symlink() or not cursor.is_dir():
            raise EvidenceVaultBundleError("Private directory ancestor is unsafe")
        for directory in reversed(missing):
            try:
                directory.mkdir(mode=0o700)
            except FileExistsError as error:
                raise EvidenceVaultBundleError(
                    f"Private path {directory} changed while it was created"
                ) from error
            directory.chmod(0o700)
            directory_descriptor = _open_directory_no_follow(directory)
            parent_descriptor = _open_directory_no_follow(directory.parent)
            try:
                os.fsync(directory_descriptor)
                os.fsync(parent_descriptor)
            except OSError as error:
                raise EvidenceVaultBundleError(
                    f"Private path {directory} could not be durably created"
                ) from error
            finally:
                os.close(directory_descriptor)
                os.close(parent_descriptor)
    try:
        _require_private_mode(path, 0o700)
    except BackupContractError as error:
        raise EvidenceVaultBundleError(str(error)) from error


def _require_private_root(root: Path) -> None:
    _assert_no_symlink_components(root)
    if root.is_symlink() or not root.is_dir():
        raise EvidenceVaultBundleError("Evidence vault root is absent or unsafe")
    try:
        _require_private_mode(root, 0o700)
    except BackupContractError as error:
        raise EvidenceVaultBundleError(str(error)) from error


def _require_private_file(path: Path) -> None:
    _assert_no_symlink_components(path)
    try:
        details = path.lstat()
    except OSError as error:
        raise EvidenceVaultBundleError(f"Private artifact {path} is absent") from error
    if not stat.S_ISREG(details.st_mode) or stat.S_IMODE(details.st_mode) != 0o600:
        raise EvidenceVaultBundleError(f"Private artifact {path} must be a mode 0600 file")


def _lstat_path_beneath(root: Path, reference: str) -> os.stat_result | None:
    cursor = root
    for index, part in enumerate(PurePosixPath(reference).parts):
        cursor = cursor / part
        try:
            details = cursor.lstat()
        except FileNotFoundError:
            return None
        if stat.S_ISLNK(details.st_mode):
            raise EvidenceVaultBundleError("Evidence vault contains a symbolic link")
        if index < len(PurePosixPath(reference).parts) - 1:
            if not stat.S_ISDIR(details.st_mode):
                raise EvidenceVaultBundleError("Evidence vault path component is not a directory")
            if stat.S_IMODE(details.st_mode) != 0o700:
                raise EvidenceVaultBundleError("Evidence vault directory is not mode 0700")
    return details


def _open_private_source(root: Path, item: dict[str, Any]) -> tuple[BinaryIO, os.stat_result]:
    reference = item["storageReference"]
    details = _lstat_path_beneath(root, reference)
    if details is None:
        raise EvidenceVaultBundleError(
            f"Required evidence bytes are absent for object {item['objectId']}"
        )
    if not stat.S_ISREG(details.st_mode) or stat.S_IMODE(details.st_mode) != 0o600:
        raise EvidenceVaultBundleError("Evidence object is not a private regular file")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(root.joinpath(*PurePosixPath(reference).parts), flags)
    except OSError as error:
        raise EvidenceVaultBundleError("Evidence object could not be opened safely") from error
    opened = os.fstat(descriptor)
    if (
        not stat.S_ISREG(opened.st_mode)
        or stat.S_IMODE(opened.st_mode) != 0o600
        or (opened.st_dev, opened.st_ino) != (details.st_dev, details.st_ino)
    ):
        os.close(descriptor)
        raise EvidenceVaultBundleError("Evidence object changed during secure open")
    return os.fdopen(descriptor, "rb", closefd=True), opened


def _zip_info(reference: str) -> zipfile.ZipInfo:
    value = zipfile.ZipInfo(reference, date_time=(1980, 1, 1, 0, 0, 0))
    value.compress_type = zipfile.ZIP_STORED
    value.create_system = 3
    value.external_attr = (stat.S_IFREG | 0o600) << 16
    value.flag_bits |= 0x800
    return value


def _copy_source_to_archive(
    archive: zipfile.ZipFile,
    root: Path,
    item: dict[str, Any],
) -> None:
    digest = hashlib.sha256()
    total = 0
    source, before = _open_private_source(root, item)
    try:
        with (
            source,
            archive.open(_zip_info(item["storageReference"]), "w", force_zip64=True) as out,
        ):
            for chunk in iter(lambda: source.read(READ_CHUNK_BYTES), b""):
                total += len(chunk)
                if total > item["byteSize"]:
                    raise EvidenceVaultBundleError("Evidence object grew during backup")
                digest.update(chunk)
                out.write(chunk)
            after = os.fstat(source.fileno())
    except OSError as error:
        raise EvidenceVaultBundleError("Unable to copy private evidence object") from error
    if (
        total != item["byteSize"]
        or digest.hexdigest() != item["contentSha256"]
        or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    ):
        raise EvidenceVaultBundleError("Evidence object measurements do not match the database")


def _database_binding(
    backup_path: Path,
    manifest_path: Path,
    verified: dict[str, Any],
) -> dict[str, Any]:
    return {
        "backup": backup_path.name,
        "manifest": manifest_path.name,
        "sha256Compressed": verified["manifest"]["sha256Compressed"],
        "sha256Manifest": _sha256_file(manifest_path),
        "sha256Rows": verified["manifest"]["sha256Rows"],
        "alembicRevisions": verified["header"].get("alembicRevisions", []),
    }


def _write_private_json_no_clobber(
    path: Path,
    payload: dict[str, Any],
) -> tuple[int, int]:
    path = _canonical_operation_path(path, label="Private JSON artifact")
    _ensure_private_directory(path.parent)
    serialized = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    parent_descriptor = _open_directory_no_follow(path.parent)
    created_identity: tuple[int, int] | None = None
    try:
        try:
            descriptor = os.open(path.name, flags, 0o600, dir_fd=parent_descriptor)
        except FileExistsError as error:
            raise EvidenceVaultBundleError(
                f"Refusing to replace existing artifact {path}"
            ) from error
        opened = os.fstat(descriptor)
        created_identity = (opened.st_dev, opened.st_ino)
        try:
            with os.fdopen(descriptor, "wb", closefd=True) as destination:
                os.fchmod(destination.fileno(), 0o600)
                destination.write(serialized)
                destination.flush()
                os.fsync(destination.fileno())
            details = os.stat(path.name, dir_fd=parent_descriptor, follow_symlinks=False)
            if (
                not stat.S_ISREG(details.st_mode)
                or stat.S_IMODE(details.st_mode) != 0o600
                or details.st_nlink != 1
                or (details.st_dev, details.st_ino) != created_identity
            ):
                raise EvidenceVaultBundleError(
                    "Private JSON artifact changed while it was written"
                )
            os.fsync(parent_descriptor)
        except BaseException:
            _unlink_if_identity(path, created_identity)
            raise
    finally:
        os.close(parent_descriptor)
    if created_identity is None:
        raise EvidenceVaultBundleError("Private JSON artifact was not created")
    return created_identity


def create_evidence_bundle(
    backup_path: Path,
    manifest_path: Path,
    vault_root: Path,
    output_directory: Path,
) -> tuple[Path, Path]:
    """Create a private archive bound to one verified logical DB backup."""

    backup_path = _canonical_operation_path(backup_path, label="Database backup")
    manifest_path = _canonical_operation_path(manifest_path, label="Database manifest")
    vault_root = _canonical_operation_path(vault_root, label="Evidence vault root")
    output_directory = _canonical_operation_path(
        output_directory,
        label="Evidence bundle output directory",
    )
    verified, inventory = derive_evidence_inventory(backup_path, manifest_path)
    included = [item for item in inventory if item["disposition"] == INCLUDED_DISPOSITION]
    if os.path.lexists(vault_root):
        _require_private_root(vault_root)
    elif included:
        raise EvidenceVaultBundleError("Evidence vault root is absent or unsafe")

    _ensure_private_directory(output_directory)
    stem = backup_path.name.removesuffix(".json.gz")
    bundle_path = output_directory / f"{stem}.family-evidence.zip"
    bundle_manifest_path = bundle_path.with_suffix(".manifest.json")
    if os.path.lexists(bundle_path) or os.path.lexists(bundle_manifest_path):
        raise EvidenceVaultBundleError("Refusing to replace an existing evidence bundle")
    temporary = output_directory / f".{bundle_path.name}.partial-{os.getpid()}-{uuid4().hex}"
    if os.path.lexists(temporary):
        raise EvidenceVaultBundleError("Evidence bundle partial path already exists")

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    temporary_identity: tuple[int, int] | None = None
    published_bundle_identity: tuple[int, int] | None = None
    published_manifest_identity: tuple[int, int] | None = None
    try:
        descriptor = os.open(temporary, flags, 0o600)
        with os.fdopen(descriptor, "w+b", closefd=True) as raw:
            os.fchmod(raw.fileno(), 0o600)
            opened = os.fstat(raw.fileno())
            temporary_identity = (opened.st_dev, opened.st_ino)
            with zipfile.ZipFile(raw, mode="w", compression=zipfile.ZIP_STORED) as archive:
                for item in included:
                    _copy_source_to_archive(archive, vault_root, item)
            raw.flush()
            os.fsync(raw.fileno())
        try:
            os.link(temporary, bundle_path, follow_symlinks=False)
        except FileExistsError as error:
            raise EvidenceVaultBundleError(
                "Refusing to replace an existing evidence bundle"
            ) from error
        published = bundle_path.lstat()
        observed_bundle_identity = (published.st_dev, published.st_ino)
        if observed_bundle_identity != temporary_identity:
            raise EvidenceVaultBundleError("Published evidence bundle identity is invalid")
        published_bundle_identity = observed_bundle_identity
        _unlink_if_identity(temporary, temporary_identity)
        if os.path.lexists(temporary):
            raise EvidenceVaultBundleError("Evidence bundle partial could not be removed safely")
        bundle_manifest = {
            "format": EVIDENCE_BUNDLE_FORMAT,
            "createdAt": datetime.now().astimezone().isoformat(),
            "bundle": bundle_path.name,
            "sha256Bundle": _sha256_file(bundle_path),
            "databaseBackup": _database_binding(
                backup_path,
                manifest_path,
                verified,
            ),
            "inventorySha256": _inventory_digest(inventory),
            "objectCount": len(inventory),
            "includedObjectCount": len(included),
            "rejectedObjectCount": sum(
                item["assessmentDecision"] == "rejected" for item in inventory
            ),
            "objects": inventory,
        }
        published_manifest_identity = _write_private_json_no_clobber(
            bundle_manifest_path,
            bundle_manifest,
        )
        verify_evidence_bundle(
            backup_path,
            manifest_path,
            bundle_path,
            bundle_manifest_path,
        )
        return bundle_path, bundle_manifest_path
    except BaseException:
        _unlink_if_identity(temporary, temporary_identity)
        _unlink_if_identity(bundle_path, published_bundle_identity)
        _unlink_if_identity(bundle_manifest_path, published_manifest_identity)
        raise


def _read_bundle_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EvidenceVaultBundleError("Evidence bundle manifest is missing or invalid") from error
    if not isinstance(value, dict) or value.get("format") != EVIDENCE_BUNDLE_FORMAT:
        raise EvidenceVaultBundleError("Unsupported evidence bundle manifest format")
    return value


def _verify_zip_inventory(
    bundle_path: Path,
    inventory: list[dict[str, Any]],
) -> None:
    included = {
        item["storageReference"]: item
        for item in inventory
        if item["disposition"] == INCLUDED_DISPOSITION
    }
    try:
        with zipfile.ZipFile(bundle_path, "r") as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(names) != len(set(names)) or set(names) != set(included):
                raise EvidenceVaultBundleError(
                    "Evidence bundle member inventory does not match the database backup"
                )
            for info in infos:
                item = included[info.filename]
                _validate_storage_reference(
                    info.filename,
                    organization_id=item["organizationId"],
                    family_id=item["familyId"],
                    object_id=item["objectId"],
                    media_type=item["mediaType"],
                )
                member_mode = info.external_attr >> 16
                if (
                    info.is_dir()
                    or stat.S_ISLNK(member_mode)
                    or not stat.S_ISREG(member_mode)
                    or stat.S_IMODE(member_mode) != 0o600
                    or info.compress_type != zipfile.ZIP_STORED
                ):
                    raise EvidenceVaultBundleError("Evidence bundle contains an unsafe member")
                if info.file_size != item["byteSize"]:
                    raise EvidenceVaultBundleError("Evidence bundle byte count is invalid")
                digest = hashlib.sha256()
                total = 0
                with archive.open(info, "r") as source:
                    for chunk in iter(lambda: source.read(READ_CHUNK_BYTES), b""):
                        total += len(chunk)
                        if total > item["byteSize"]:
                            raise EvidenceVaultBundleError(
                                "Evidence bundle member exceeds its bound"
                            )
                        digest.update(chunk)
                if total != item["byteSize"] or digest.hexdigest() != item["contentSha256"]:
                    raise EvidenceVaultBundleError("Evidence bundle object digest is invalid")
            if archive.testzip() is not None:
                raise EvidenceVaultBundleError("Evidence bundle CRC verification failed")
    except (OSError, zipfile.BadZipFile, RuntimeError) as error:
        if isinstance(error, EvidenceVaultBundleError):
            raise
        raise EvidenceVaultBundleError("Evidence bundle archive is invalid") from error


def verify_evidence_bundle(
    backup_path: Path,
    manifest_path: Path,
    bundle_path: Path,
    bundle_manifest_path: Path,
) -> dict[str, Any]:
    """Verify DB binding, exact inventory, archive membership, bytes, and modes."""

    backup_path = _canonical_operation_path(backup_path, label="Database backup")
    manifest_path = _canonical_operation_path(manifest_path, label="Database manifest")
    bundle_path = _canonical_operation_path(bundle_path, label="Evidence bundle")
    bundle_manifest_path = _canonical_operation_path(
        bundle_manifest_path,
        label="Evidence bundle manifest",
    )
    verified, inventory = derive_evidence_inventory(backup_path, manifest_path)
    _ensure_private_directory(bundle_path.parent)
    _ensure_private_directory(bundle_manifest_path.parent)
    _require_private_file(bundle_path)
    _require_private_file(bundle_manifest_path)
    value = _read_bundle_manifest(bundle_manifest_path)
    expected_binding = _database_binding(backup_path, manifest_path, verified)
    if value.get("bundle") != bundle_path.name:
        raise EvidenceVaultBundleError("Evidence manifest names a different bundle")
    if value.get("sha256Bundle") != _sha256_file(bundle_path):
        raise EvidenceVaultBundleError("Evidence bundle SHA-256 mismatch")
    if value.get("databaseBackup") != expected_binding:
        raise EvidenceVaultBundleError("Evidence bundle is bound to a different database backup")
    if value.get("objects") != inventory:
        raise EvidenceVaultBundleError("Evidence bundle inventory differs from the DB snapshot")
    if value.get("inventorySha256") != _inventory_digest(inventory):
        raise EvidenceVaultBundleError("Evidence bundle inventory SHA-256 mismatch")
    included_count = sum(item["disposition"] == INCLUDED_DISPOSITION for item in inventory)
    rejected_count = sum(item["assessmentDecision"] == "rejected" for item in inventory)
    if (
        value.get("objectCount") != len(inventory)
        or value.get("includedObjectCount") != included_count
        or value.get("rejectedObjectCount") != rejected_count
    ):
        raise EvidenceVaultBundleError("Evidence bundle inventory counts are invalid")
    _verify_zip_inventory(bundle_path, inventory)
    return {
        "manifest": value,
        "objects": inventory,
        "objectCount": len(inventory),
        "includedObjectCount": included_count,
        "rejectedObjectCount": rejected_count,
    }


def _create_restore_file(root: Path, reference: str) -> tuple[BinaryIO, Path]:
    parts = PurePosixPath(reference).parts
    parent = root
    for part in parts[:-1]:
        parent = parent / part
        if os.path.lexists(parent):
            if parent.is_symlink() or not parent.is_dir():
                raise EvidenceVaultBundleError("Restore path contains an unsafe component")
        else:
            parent.mkdir(mode=0o700)
        parent.chmod(0o700)
    target = parent / parts[-1]
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(target, flags, 0o600)
    except FileExistsError as error:
        raise EvidenceVaultBundleError(
            "Restore would replace an existing evidence object"
        ) from error
    return os.fdopen(descriptor, "wb", closefd=True), target


def _verify_restored_vault(
    destination: Path,
    inventory: list[dict[str, Any]],
) -> None:
    expected = {
        item["storageReference"]: item
        for item in inventory
        if item["disposition"] == INCLUDED_DISPOSITION
    }
    found: set[str] = set()
    for directory, directory_names, filenames in os.walk(destination, followlinks=False):
        current = Path(directory)
        details = current.lstat()
        if not stat.S_ISDIR(details.st_mode) or stat.S_IMODE(details.st_mode) != 0o700:
            raise EvidenceVaultBundleError("Restored vault directory mode is invalid")
        for name in directory_names:
            child = current / name
            if child.is_symlink():
                raise EvidenceVaultBundleError("Restored vault contains a symbolic link")
        for name in filenames:
            child = current / name
            details = child.lstat()
            if not stat.S_ISREG(details.st_mode) or stat.S_IMODE(details.st_mode) != 0o600:
                raise EvidenceVaultBundleError("Restored vault file mode is invalid")
            reference = child.relative_to(destination).as_posix()
            item = expected.get(reference)
            if item is None:
                raise EvidenceVaultBundleError("Restored vault contains an unexpected object")
            digest = hashlib.sha256()
            total = 0
            with child.open("rb") as source:
                for chunk in iter(lambda: source.read(READ_CHUNK_BYTES), b""):
                    total += len(chunk)
                    digest.update(chunk)
            if total != item["byteSize"] or digest.hexdigest() != item["contentSha256"]:
                raise EvidenceVaultBundleError("Restored evidence measurements are invalid")
            found.add(reference)
    if found != set(expected):
        raise EvidenceVaultBundleError("Restored vault is missing an evidence object")


def _fsync_restored_vault_tree(destination: Path) -> None:
    """Durably publish file and directory entries before any restore receipt."""

    directories = [Path(directory) for directory, _, _ in os.walk(destination)]
    for directory in sorted(directories, key=lambda value: len(value.parts), reverse=True):
        descriptor = _open_directory_no_follow(directory)
        try:
            os.fsync(descriptor)
        except OSError as error:
            raise EvidenceVaultBundleError(
                "Restored evidence directory could not be synchronized"
            ) from error
        finally:
            os.close(descriptor)
    parent_descriptor = _open_directory_no_follow(destination.parent)
    try:
        os.fsync(parent_descriptor)
    except OSError as error:
        raise EvidenceVaultBundleError(
            "Restored evidence root entry could not be synchronized"
        ) from error
    finally:
        os.close(parent_descriptor)


def restore_evidence_bundle(
    backup_path: Path,
    manifest_path: Path,
    bundle_path: Path,
    bundle_manifest_path: Path,
    destination: Path,
    *,
    receipt_path: Path | None = None,
) -> dict[str, Any]:
    """Restore only into a new disposable vault root and verify every byte."""

    backup_path = _canonical_operation_path(backup_path, label="Database backup")
    manifest_path = _canonical_operation_path(manifest_path, label="Database manifest")
    bundle_path = _canonical_operation_path(bundle_path, label="Evidence bundle")
    bundle_manifest_path = _canonical_operation_path(
        bundle_manifest_path,
        label="Evidence bundle manifest",
    )
    destination = _canonical_operation_path(
        destination,
        label="Disposable evidence restore destination",
    )
    if receipt_path is not None:
        receipt_path = _canonical_operation_path(
            receipt_path,
            label="Evidence restore receipt",
        )
    verified = verify_evidence_bundle(
        backup_path,
        manifest_path,
        bundle_path,
        bundle_manifest_path,
    )
    if os.path.lexists(destination):
        raise EvidenceVaultBundleError("Disposable evidence restore destination already exists")
    if receipt_path is not None and os.path.lexists(receipt_path):
        raise EvidenceVaultBundleError("Restore receipt already exists")
    destination_absolute = Path(os.path.abspath(destination.expanduser()))
    if receipt_path is not None:
        receipt_absolute = Path(os.path.abspath(receipt_path.expanduser()))
        if (
            receipt_absolute == destination_absolute
            or destination_absolute in receipt_absolute.parents
        ):
            raise EvidenceVaultBundleError("Restore receipt cannot be written inside the vault")
    _ensure_private_directory(destination.parent)
    try:
        destination.mkdir(mode=0o700)
    except FileExistsError as error:
        raise EvidenceVaultBundleError(
            "Disposable evidence restore destination already exists"
        ) from error
    destination.chmod(0o700)

    included = {
        item["storageReference"]: item
        for item in verified["objects"]
        if item["disposition"] == INCLUDED_DISPOSITION
    }
    try:
        with zipfile.ZipFile(bundle_path, "r") as archive:
            for reference in sorted(included):
                item = included[reference]
                destination_file, target = _create_restore_file(destination, reference)
                digest = hashlib.sha256()
                total = 0
                try:
                    with destination_file, archive.open(reference, "r") as source:
                        for chunk in iter(lambda: source.read(READ_CHUNK_BYTES), b""):
                            total += len(chunk)
                            if total > item["byteSize"]:
                                raise EvidenceVaultBundleError(
                                    "Restore member exceeds its database byte bound"
                                )
                            digest.update(chunk)
                            destination_file.write(chunk)
                        destination_file.flush()
                        os.fsync(destination_file.fileno())
                    target.chmod(0o600)
                except BaseException:
                    target.unlink(missing_ok=True)
                    raise
                if total != item["byteSize"] or digest.hexdigest() != item["contentSha256"]:
                    raise EvidenceVaultBundleError("Restored evidence digest is invalid")
        _verify_restored_vault(destination, verified["objects"])
        _fsync_restored_vault_tree(destination)
        result = {
            "format": EVIDENCE_RESTORE_RECEIPT_FORMAT,
            "verifiedAt": datetime.now().astimezone().isoformat(),
            "databaseBackup": verified["manifest"]["databaseBackup"],
            "bundle": bundle_path.name,
            "bundleSha256": verified["manifest"]["sha256Bundle"],
            "inventorySha256": verified["manifest"]["inventorySha256"],
            "objectCount": verified["objectCount"],
            "restoredObjectCount": verified["includedObjectCount"],
            "rejectedObjectCount": verified["rejectedObjectCount"],
        }
        if receipt_path is not None:
            _write_private_json_no_clobber(receipt_path, result)
        return result
    except BaseException:
        shutil.rmtree(destination, ignore_errors=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create")
    create_parser.add_argument("--backup", type=Path, required=True)
    create_parser.add_argument("--manifest", type=Path, required=True)
    create_parser.add_argument("--vault-root", type=Path, default=DEFAULT_VAULT_ROOT)
    create_parser.add_argument("--output-directory", type=Path, required=True)

    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--backup", type=Path, required=True)
    verify_parser.add_argument("--manifest", type=Path, required=True)
    verify_parser.add_argument("--bundle", type=Path, required=True)
    verify_parser.add_argument("--bundle-manifest", type=Path, required=True)

    restore_parser = subparsers.add_parser("restore")
    restore_parser.add_argument("--backup", type=Path, required=True)
    restore_parser.add_argument("--manifest", type=Path, required=True)
    restore_parser.add_argument("--bundle", type=Path, required=True)
    restore_parser.add_argument("--bundle-manifest", type=Path, required=True)
    restore_parser.add_argument("--destination", type=Path, required=True)
    restore_parser.add_argument("--receipt", type=Path)

    args = parser.parse_args()
    if args.command == "create":
        bundle, bundle_manifest = create_evidence_bundle(
            args.backup,
            args.manifest,
            args.vault_root,
            args.output_directory,
        )
        print(f"Evidence bundle created: {bundle}")
        print(f"Evidence bundle manifest created: {bundle_manifest}")
    elif args.command == "verify":
        result = verify_evidence_bundle(
            args.backup,
            args.manifest,
            args.bundle,
            args.bundle_manifest,
        )
        print(f"Evidence bundle verified: {result['objectCount']} objects")
    else:
        result = restore_evidence_bundle(
            args.backup,
            args.manifest,
            args.bundle,
            args.bundle_manifest,
            args.destination,
            receipt_path=args.receipt,
        )
        print(
            "Disposable evidence vault restored and verified: "
            f"{result['restoredObjectCount']} objects"
        )


if __name__ == "__main__":
    main()
