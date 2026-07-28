"""Create, verify, and restore a backup-bound encrypted staff/transport vault.

The verified logical database backup is the only inventory authority. This
tool never opens a live database, loads encryption keys, decrypts evidence, or
prints object references. Every ciphertext referenced by the 0030/0032 tables
is retained, including historical, rejected, expired, and revoked versions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import zipfile
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import uuid4

from scripts.family_evidence_vault_bundle import (
    EvidenceVaultBundleError as FamilyEvidenceVaultBundleError,
)
from scripts.family_evidence_vault_bundle import (
    _canonical_operation_path,
    _ensure_private_directory,
    _fsync_restored_vault_tree,
    _open_directory_no_follow,
    _require_private_file,
    _unlink_if_identity,
    _write_private_json_no_clobber,
)
from scripts.staff_transport_vault_preflight import (
    ENCRYPTED_CONTAINER_OVERHEAD_BYTES,
    MAXIMUM_CIPHERTEXT_BYTES,
    StaffTransportVaultPreflightError,
    _analyze_vault,
    _canonical_reference_parts,
    _directory_flags,
    _file_flags,
    _hash_pinned_artifact,
    _mode,
    _open_directory_path_no_follow,
    _pin_private_artifact,
    _read_pinned_bytes,
    _recheck_pinned_artifact,
    _stable_stat,
    pinned_staff_transport_inventory,
)

BUNDLE_FORMAT = "caresync-staff-transport-vault-bundle-v1"
RESTORE_RECEIPT_FORMAT = "caresync-staff-transport-vault-restore-v1"
READ_CHUNK_BYTES = 1024 * 1024
MAXIMUM_BUNDLE_MANIFEST_BYTES = 64 * 1024 * 1024
DEFAULT_VAULT_ROOT = (
    Path.home()
    / "Library"
    / "Application Support"
    / "CareSync Basic"
    / "private-staff-screening-vault"
)


class StaffTransportVaultBundleError(RuntimeError):
    """Raised when a private recovery bundle cannot be proved exact."""


@contextmanager
def _translate_dependency_errors():
    try:
        yield
    except StaffTransportVaultBundleError:
        raise
    except (
        StaffTransportVaultPreflightError,
        FamilyEvidenceVaultBundleError,
    ) as error:
        raise StaffTransportVaultBundleError(str(error)) from error


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _inventory(projection: dict[str, Any]) -> list[dict[str, Any]]:
    inventory = projection.get("inventory")
    if not isinstance(inventory, dict) or not isinstance(inventory.get("objects"), list):
        raise StaffTransportVaultBundleError("Backup-derived encrypted inventory is malformed")
    return inventory["objects"]


def _expected_references(projection: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in _inventory(projection):
        reference = item.get("storageReference")
        if not isinstance(reference, str):
            raise StaffTransportVaultBundleError(
                "Backup-derived encrypted storage reference is malformed"
            )
        _canonical_reference_parts(reference)
        if reference in result:
            raise StaffTransportVaultBundleError(
                "Backup-derived encrypted inventory contains a duplicate object"
            )
        result[reference] = item
    return result


def _require_exact_analysis(
    analysis: dict[str, Any],
    *,
    object_count: int,
) -> None:
    absent_empty_vault = (
        object_count == 0
        and analysis.get("expectedCount") == 0
        and analysis.get("presentCount") == 0
        and analysis.get("missing") == []
        and analysis.get("mismatch") == []
        and analysis.get("unexpected") == []
        and analysis.get("indeterminate") == []
        and analysis.get("unsafe") == [{"reference": ".", "reason": "vault_root_absent"}]
    )
    if absent_empty_vault:
        return
    issue_fields = ("missing", "mismatch", "unsafe", "unexpected", "indeterminate")
    if (
        analysis.get("expectedCount") != object_count
        or analysis.get("presentCount") != object_count
        or any(analysis.get(field) != [] for field in issue_fields)
        or (object_count > 0 and not isinstance(analysis.get("vaultIdentity"), dict))
    ):
        counts = ", ".join(
            f"{field}={len(analysis.get(field, []))}"
            for field in issue_fields
            if isinstance(analysis.get(field), list)
        )
        raise StaffTransportVaultBundleError(
            "Encrypted vault does not exactly match the verified backup inventory"
            + (f" ({counts})" if counts else "")
        )


def _zip_info(reference: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(reference, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o600) << 16
    info.flag_bits |= 0x800
    return info


def _open_ciphertext(
    root_descriptor: int,
    root_details: os.stat_result,
    reference: str,
) -> tuple[int, list[tuple[int, os.stat_result]], os.stat_result]:
    descriptors: list[tuple[int, os.stat_result]] = []
    current = root_descriptor
    expected_owner = os.geteuid() if hasattr(os, "geteuid") else root_details.st_uid
    try:
        for part in PurePosixPath(reference).parts[:-1]:
            child = os.open(part, _directory_flags(), dir_fd=current)
            details = os.fstat(child)
            if (
                not stat.S_ISDIR(details.st_mode)
                or _mode(details) != 0o700
                or details.st_uid != expected_owner
                or details.st_dev != root_details.st_dev
            ):
                os.close(child)
                raise StaffTransportVaultBundleError(
                    "Encrypted vault directory is not a private owned directory"
                )
            descriptors.append((child, details))
            current = child
        file_descriptor = os.open(
            PurePosixPath(reference).parts[-1],
            _file_flags(),
            dir_fd=current,
        )
        details = os.fstat(file_descriptor)
        if (
            not stat.S_ISREG(details.st_mode)
            or _mode(details) != 0o600
            or details.st_uid != expected_owner
            or details.st_nlink != 1
            or details.st_dev != root_details.st_dev
        ):
            os.close(file_descriptor)
            raise StaffTransportVaultBundleError(
                "Encrypted evidence object is not a private owned single-link file"
            )
        return file_descriptor, descriptors, details
    except OSError as error:
        for descriptor, _details in reversed(descriptors):
            os.close(descriptor)
        raise StaffTransportVaultBundleError(
            "Encrypted evidence object could not be opened without following links"
        ) from error
    except BaseException:
        for descriptor, _details in reversed(descriptors):
            os.close(descriptor)
        raise


def _copy_ciphertext(
    archive: zipfile.ZipFile,
    root_descriptor: int,
    root_details: os.stat_result,
    item: dict[str, Any],
) -> None:
    reference = item["storageReference"]
    _canonical_reference_parts(reference)
    expected_size = item["ciphertextByteSize"]
    if (
        isinstance(expected_size, bool)
        or not isinstance(expected_size, int)
        or not ENCRYPTED_CONTAINER_OVERHEAD_BYTES < expected_size <= MAXIMUM_CIPHERTEXT_BYTES
    ):
        raise StaffTransportVaultBundleError(
            "Backup-derived ciphertext byte measurement is invalid"
        )
    expected_digest = item["ciphertextSha256"]
    file_descriptor, directories, before = _open_ciphertext(
        root_descriptor,
        root_details,
        reference,
    )
    digest = hashlib.sha256()
    total = 0
    try:
        if before.st_size != expected_size:
            raise StaffTransportVaultBundleError(
                "Encrypted evidence byte size differs from the verified backup"
            )
        with archive.open(_zip_info(reference), "w", force_zip64=True) as destination:
            while True:
                chunk = os.read(file_descriptor, READ_CHUNK_BYTES)
                if not chunk:
                    break
                total += len(chunk)
                if total > expected_size:
                    raise StaffTransportVaultBundleError(
                        "Encrypted evidence object exceeded its verified byte bound"
                    )
                digest.update(chunk)
                destination.write(chunk)
        after = os.fstat(file_descriptor)
        if (
            total != expected_size
            or digest.hexdigest() != expected_digest
            or _stable_stat(after) != _stable_stat(before)
            or any(
                _stable_stat(os.fstat(descriptor)) != _stable_stat(opened)
                for descriptor, opened in directories
            )
            or _stable_stat(os.fstat(root_descriptor)) != _stable_stat(root_details)
        ):
            raise StaffTransportVaultBundleError(
                "Encrypted evidence changed or differs from verified database metadata"
            )
    except OSError as error:
        raise StaffTransportVaultBundleError(
            "Encrypted evidence could not be copied durably"
        ) from error
    finally:
        os.close(file_descriptor)
        for descriptor, _details in reversed(directories):
            os.close(descriptor)


def _manifest_payload(
    projection: dict[str, Any],
    *,
    bundle_name: str,
    bundle_sha256: str,
) -> dict[str, Any]:
    inventory = projection["inventory"]
    return {
        "format": BUNDLE_FORMAT,
        "bundle": bundle_name,
        "sha256Bundle": bundle_sha256,
        "databaseBackup": projection["databaseBackup"],
        "inventorySha256": inventory["sha256"],
        "uniqueObjectCount": inventory["uniqueObjectCount"],
        "ownershipRelationshipCount": inventory["ownershipRelationshipCount"],
        "sourceRowCounts": inventory["sourceRowCounts"],
        "keyIdCounts": inventory["keyIdCounts"],
        "objects": inventory["objects"],
        "retentionPolicy": "all_backup_referenced_ciphertext",
        "databaseVaultConsistencyAuthority": False,
        "purgeAuthority": False,
        "limitation": "logical_backup_snapshot_boundary_unproven",
    }


def _read_pinned_manifest(artifact) -> dict[str, Any]:
    content = _read_pinned_bytes(
        artifact,
        maximum_bytes=MAXIMUM_BUNDLE_MANIFEST_BYTES,
    )
    try:
        value = json.loads(content)
    except json.JSONDecodeError as error:
        raise StaffTransportVaultBundleError(
            "Encrypted vault bundle manifest is invalid"
        ) from error
    if not isinstance(value, dict) or value.get("format") != BUNDLE_FORMAT:
        raise StaffTransportVaultBundleError(
            "Encrypted vault bundle manifest format is unsupported"
        )
    return value


def _verify_zip(
    bundle_artifact,
    expected: dict[str, dict[str, Any]],
) -> None:
    try:
        os.lseek(bundle_artifact.descriptor, 0, os.SEEK_SET)
        with (
            os.fdopen(os.dup(bundle_artifact.descriptor), "rb", closefd=True) as source,
            zipfile.ZipFile(source, "r") as archive,
        ):
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if (
                len(names) != len(set(names))
                or set(names) != set(expected)
                or archive.comment != b""
            ):
                raise StaffTransportVaultBundleError(
                    "Encrypted vault archive inventory is not exact"
                )
            for info in infos:
                item = expected[info.filename]
                _canonical_reference_parts(info.filename)
                member_mode = info.external_attr >> 16
                if (
                    info.is_dir()
                    or stat.S_ISLNK(member_mode)
                    or not stat.S_ISREG(member_mode)
                    or stat.S_IMODE(member_mode) != 0o600
                    or info.compress_type != zipfile.ZIP_STORED
                    or info.date_time != (1980, 1, 1, 0, 0, 0)
                    or info.extra != b""
                    or info.file_size != item["ciphertextByteSize"]
                ):
                    raise StaffTransportVaultBundleError(
                        "Encrypted vault archive contains an unsafe or nondeterministic member"
                    )
                digest = hashlib.sha256()
                total = 0
                with archive.open(info, "r") as member:
                    while True:
                        chunk = member.read(READ_CHUNK_BYTES)
                        if not chunk:
                            break
                        total += len(chunk)
                        if total > item["ciphertextByteSize"]:
                            raise StaffTransportVaultBundleError(
                                "Encrypted vault archive member exceeded its byte bound"
                            )
                        digest.update(chunk)
                if (
                    total != item["ciphertextByteSize"]
                    or digest.hexdigest() != item["ciphertextSha256"]
                ):
                    raise StaffTransportVaultBundleError(
                        "Encrypted vault archive ciphertext measurement is invalid"
                    )
            if archive.testzip() is not None:
                raise StaffTransportVaultBundleError(
                    "Encrypted vault archive CRC verification failed"
                )
    except (OSError, RuntimeError, zipfile.BadZipFile) as error:
        if isinstance(error, StaffTransportVaultBundleError):
            raise
        raise StaffTransportVaultBundleError(
            "Encrypted vault archive is unreadable or invalid"
        ) from error
    finally:
        os.lseek(bundle_artifact.descriptor, 0, os.SEEK_SET)


def _verify_bundle_against_projection(
    projection: dict[str, Any],
    bundle_path: Path,
    bundle_manifest_path: Path,
) -> dict[str, Any]:
    _require_private_file(bundle_path)
    _require_private_file(bundle_manifest_path)
    bundle_artifact = _pin_private_artifact(bundle_path, label="Encrypted vault bundle")
    try:
        manifest_artifact = _pin_private_artifact(
            bundle_manifest_path,
            label="Encrypted vault bundle manifest",
        )
        try:
            manifest = _read_pinned_manifest(manifest_artifact)
            bundle_sha256 = _hash_pinned_artifact(bundle_artifact)
            expected_manifest = _manifest_payload(
                projection,
                bundle_name=bundle_path.name,
                bundle_sha256=bundle_sha256,
            )
            if manifest != expected_manifest:
                raise StaffTransportVaultBundleError(
                    "Encrypted vault bundle manifest differs from the verified backup"
                )
            _verify_zip(bundle_artifact, _expected_references(projection))
            _recheck_pinned_artifact(
                bundle_artifact,
                label="Encrypted vault bundle",
            )
            _recheck_pinned_artifact(
                manifest_artifact,
                label="Encrypted vault bundle manifest",
            )
            return {
                "manifest": manifest,
                "objects": projection["inventory"]["objects"],
                "uniqueObjectCount": projection["inventory"]["uniqueObjectCount"],
                "ownershipRelationshipCount": projection["inventory"]["ownershipRelationshipCount"],
            }
        finally:
            manifest_artifact.close()
    finally:
        bundle_artifact.close()


def create_staff_transport_vault_bundle(
    backup_path: Path,
    manifest_path: Path,
    vault_root: Path,
    output_directory: Path,
) -> tuple[Path, Path]:
    """Create one deterministic, private, no-clobber recovery bundle."""

    with _translate_dependency_errors():
        backup_path = _canonical_operation_path(backup_path, label="Database backup")
        manifest_path = _canonical_operation_path(
            manifest_path,
            label="Database manifest",
        )
        vault_root = _canonical_operation_path(vault_root, label="Encrypted vault root")
        output_directory = _canonical_operation_path(
            output_directory,
            label="Encrypted vault bundle output directory",
        )
        if output_directory == vault_root or vault_root in output_directory.parents:
            raise StaffTransportVaultBundleError(
                "Encrypted vault bundles cannot be written inside the live vault"
            )
        _ensure_private_directory(output_directory)
        stem = backup_path.name.removesuffix(".json.gz")
        bundle_path = output_directory / f"{stem}.staff-transport-evidence.zip"
        bundle_manifest_path = bundle_path.with_suffix(".manifest.json")
        if os.path.lexists(bundle_path) or os.path.lexists(bundle_manifest_path):
            raise StaffTransportVaultBundleError(
                "Refusing to replace an existing encrypted vault bundle"
            )

        temporary = output_directory / (f".{bundle_path.name}.partial-{os.getpid()}-{uuid4().hex}")
        temporary_identity: tuple[int, int] | None = None
        bundle_identity: tuple[int, int] | None = None
        manifest_identity: tuple[int, int] | None = None
        try:
            with pinned_staff_transport_inventory(
                backup_path,
                manifest_path,
            ) as projection:
                objects = _expected_references(projection)
                before_analysis = _analyze_vault(
                    projection["inventory"]["objects"],
                    vault_root,
                )
                _require_exact_analysis(before_analysis, object_count=len(objects))

                output_descriptor = _open_directory_no_follow(output_directory)
                root_descriptor: int | None = None
                try:
                    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL
                    if hasattr(os, "O_NOFOLLOW"):
                        flags |= os.O_NOFOLLOW
                    if hasattr(os, "O_CLOEXEC"):
                        flags |= os.O_CLOEXEC
                    descriptor = os.open(
                        temporary.name,
                        flags,
                        0o600,
                        dir_fd=output_descriptor,
                    )
                    with os.fdopen(descriptor, "w+b", closefd=True) as raw:
                        os.fchmod(raw.fileno(), 0o600)
                        opened = os.fstat(raw.fileno())
                        temporary_identity = (opened.st_dev, opened.st_ino)
                        if objects:
                            root_descriptor = _open_directory_path_no_follow(
                                vault_root,
                                label="Encrypted vault root",
                            )
                            root_details = os.fstat(root_descriptor)
                            expected_owner = (
                                os.geteuid() if hasattr(os, "geteuid") else root_details.st_uid
                            )
                            if (
                                not stat.S_ISDIR(root_details.st_mode)
                                or _mode(root_details) != 0o700
                                or root_details.st_uid != expected_owner
                            ):
                                raise StaffTransportVaultBundleError(
                                    "Encrypted vault root is not a private owned directory"
                                )
                        with zipfile.ZipFile(
                            raw,
                            mode="w",
                            compression=zipfile.ZIP_STORED,
                        ) as archive:
                            archive.comment = b""
                            if root_descriptor is not None:
                                for item in projection["inventory"]["objects"]:
                                    _copy_ciphertext(
                                        archive,
                                        root_descriptor,
                                        root_details,
                                        item,
                                    )
                        raw.flush()
                        os.fsync(raw.fileno())
                    try:
                        os.link(
                            temporary.name,
                            bundle_path.name,
                            src_dir_fd=output_descriptor,
                            dst_dir_fd=output_descriptor,
                            follow_symlinks=False,
                        )
                    except FileExistsError as error:
                        raise StaffTransportVaultBundleError(
                            "Refusing to replace an existing encrypted vault bundle"
                        ) from error
                    published = os.stat(
                        bundle_path.name,
                        dir_fd=output_descriptor,
                        follow_symlinks=False,
                    )
                    bundle_identity = (published.st_dev, published.st_ino)
                    if (
                        bundle_identity != temporary_identity
                        or not stat.S_ISREG(published.st_mode)
                        or _mode(published) != 0o600
                        or published.st_nlink != 2
                    ):
                        raise StaffTransportVaultBundleError(
                            "Encrypted vault bundle publication identity is invalid"
                        )
                    os.unlink(temporary.name, dir_fd=output_descriptor)
                    os.fsync(output_descriptor)
                    if os.path.lexists(temporary):
                        raise StaffTransportVaultBundleError(
                            "Encrypted vault partial artifact remains after publication"
                        )
                finally:
                    if root_descriptor is not None:
                        os.close(root_descriptor)
                    os.close(output_descriptor)

                after_analysis = _analyze_vault(
                    projection["inventory"]["objects"],
                    vault_root,
                )
                _require_exact_analysis(after_analysis, object_count=len(objects))
                if before_analysis.get("vaultIdentity") != after_analysis.get("vaultIdentity"):
                    raise StaffTransportVaultBundleError(
                        "Encrypted vault identity changed while the bundle was created"
                    )

                published_artifact = _pin_private_artifact(
                    bundle_path,
                    label="Encrypted vault bundle",
                )
                try:
                    bundle_sha256 = _hash_pinned_artifact(published_artifact)
                    _recheck_pinned_artifact(
                        published_artifact,
                        label="Encrypted vault bundle",
                    )
                finally:
                    published_artifact.close()
                manifest_payload = _manifest_payload(
                    projection,
                    bundle_name=bundle_path.name,
                    bundle_sha256=bundle_sha256,
                )
                manifest_identity = _write_private_json_no_clobber(
                    bundle_manifest_path,
                    manifest_payload,
                )
                _verify_bundle_against_projection(
                    projection,
                    bundle_path,
                    bundle_manifest_path,
                )
            return bundle_path, bundle_manifest_path
        except BaseException:
            _unlink_if_identity(temporary, temporary_identity)
            _unlink_if_identity(bundle_path, bundle_identity)
            _unlink_if_identity(bundle_manifest_path, manifest_identity)
            raise


def verify_staff_transport_vault_bundle(
    backup_path: Path,
    manifest_path: Path,
    bundle_path: Path,
    bundle_manifest_path: Path,
) -> dict[str, Any]:
    """Verify DB binding, deterministic membership, modes, sizes, and digests."""

    with _translate_dependency_errors():
        backup_path = _canonical_operation_path(backup_path, label="Database backup")
        manifest_path = _canonical_operation_path(
            manifest_path,
            label="Database manifest",
        )
        bundle_path = _canonical_operation_path(
            bundle_path,
            label="Encrypted vault bundle",
        )
        bundle_manifest_path = _canonical_operation_path(
            bundle_manifest_path,
            label="Encrypted vault bundle manifest",
        )
        with pinned_staff_transport_inventory(
            backup_path,
            manifest_path,
        ) as projection:
            return _verify_bundle_against_projection(
                projection,
                bundle_path,
                bundle_manifest_path,
            )


def _restore_member(
    root_descriptor: int,
    root_details: os.stat_result,
    archive: zipfile.ZipFile,
    reference: str,
    item: dict[str, Any],
) -> None:
    descriptors: list[int] = []
    current = root_descriptor
    try:
        for part in PurePosixPath(reference).parts[:-1]:
            try:
                os.mkdir(part, 0o700, dir_fd=current)
                os.fsync(current)
            except FileExistsError:
                pass
            child = os.open(part, _directory_flags(), dir_fd=current)
            details = os.fstat(child)
            expected_owner = os.geteuid() if hasattr(os, "geteuid") else details.st_uid
            if (
                not stat.S_ISDIR(details.st_mode)
                or _mode(details) != 0o700
                or details.st_uid != expected_owner
                or details.st_dev != root_details.st_dev
            ):
                os.close(child)
                raise StaffTransportVaultBundleError(
                    "Disposable restore contains an unsafe directory"
                )
            descriptors.append(child)
            current = child
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        try:
            target_descriptor = os.open(
                PurePosixPath(reference).parts[-1],
                flags,
                0o600,
                dir_fd=current,
            )
        except FileExistsError as error:
            raise StaffTransportVaultBundleError(
                "Disposable restore would replace an encrypted evidence object"
            ) from error
        digest = hashlib.sha256()
        total = 0
        try:
            os.fchmod(target_descriptor, 0o600)
            with archive.open(reference, "r") as source:
                while True:
                    chunk = source.read(READ_CHUNK_BYTES)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > item["ciphertextByteSize"]:
                        raise StaffTransportVaultBundleError(
                            "Restored encrypted object exceeded its database byte bound"
                        )
                    digest.update(chunk)
                    remaining = memoryview(chunk)
                    while remaining:
                        written = os.write(target_descriptor, remaining)
                        if written < 1:
                            raise OSError("Restore write made no progress")
                        remaining = remaining[written:]
            os.fsync(target_descriptor)
            details = os.fstat(target_descriptor)
            if (
                not stat.S_ISREG(details.st_mode)
                or _mode(details) != 0o600
                or details.st_nlink != 1
                or total != item["ciphertextByteSize"]
                or details.st_size != total
                or digest.hexdigest() != item["ciphertextSha256"]
            ):
                raise StaffTransportVaultBundleError(
                    "Restored encrypted evidence measurement is invalid"
                )
        finally:
            os.close(target_descriptor)
        os.fsync(current)
    except OSError as error:
        raise StaffTransportVaultBundleError(
            "Encrypted evidence restore could not be written durably"
        ) from error
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _remove_restore_if_identity(
    destination: Path,
    identity: tuple[int, int] | None,
) -> None:
    if identity is None:
        return
    try:
        details = destination.lstat()
    except OSError:
        return
    if (details.st_dev, details.st_ino) != identity or not stat.S_ISDIR(details.st_mode):
        return
    shutil.rmtree(destination, ignore_errors=True)


def restore_staff_transport_vault_bundle(
    backup_path: Path,
    manifest_path: Path,
    bundle_path: Path,
    bundle_manifest_path: Path,
    destination: Path,
    *,
    receipt_path: Path | None = None,
) -> dict[str, Any]:
    """Restore only into one new private root and remeasure the exact inventory."""

    with _translate_dependency_errors():
        backup_path = _canonical_operation_path(backup_path, label="Database backup")
        manifest_path = _canonical_operation_path(
            manifest_path,
            label="Database manifest",
        )
        bundle_path = _canonical_operation_path(
            bundle_path,
            label="Encrypted vault bundle",
        )
        bundle_manifest_path = _canonical_operation_path(
            bundle_manifest_path,
            label="Encrypted vault bundle manifest",
        )
        destination = _canonical_operation_path(
            destination,
            label="Disposable encrypted vault restore destination",
        )
        if receipt_path is not None:
            receipt_path = _canonical_operation_path(
                receipt_path,
                label="Encrypted vault restore receipt",
            )
        if os.path.lexists(destination):
            raise StaffTransportVaultBundleError(
                "Disposable encrypted vault restore destination already exists"
            )
        if receipt_path is not None and os.path.lexists(receipt_path):
            raise StaffTransportVaultBundleError("Encrypted vault restore receipt already exists")
        if receipt_path is not None and (
            receipt_path == destination or destination in receipt_path.parents
        ):
            raise StaffTransportVaultBundleError(
                "Encrypted vault restore receipt cannot be written inside the vault"
            )
        _ensure_private_directory(destination.parent)

        destination_identity: tuple[int, int] | None = None
        receipt_identity: tuple[int, int] | None = None
        try:
            with pinned_staff_transport_inventory(
                backup_path,
                manifest_path,
            ) as projection:
                verified = _verify_bundle_against_projection(
                    projection,
                    bundle_path,
                    bundle_manifest_path,
                )
                destination_parent = _open_directory_no_follow(destination.parent)
                try:
                    os.mkdir(destination.name, 0o700, dir_fd=destination_parent)
                    created = os.stat(
                        destination.name,
                        dir_fd=destination_parent,
                        follow_symlinks=False,
                    )
                    if not stat.S_ISDIR(created.st_mode) or _mode(created) != 0o700:
                        raise StaffTransportVaultBundleError(
                            "Disposable encrypted vault root was not created privately"
                        )
                    destination_identity = (created.st_dev, created.st_ino)
                    os.fsync(destination_parent)
                except FileExistsError as error:
                    raise StaffTransportVaultBundleError(
                        "Disposable encrypted vault restore destination already exists"
                    ) from error
                finally:
                    os.close(destination_parent)

                bundle_artifact = _pin_private_artifact(
                    bundle_path,
                    label="Encrypted vault bundle",
                )
                try:
                    if (
                        _hash_pinned_artifact(bundle_artifact)
                        != verified["manifest"]["sha256Bundle"]
                    ):
                        raise StaffTransportVaultBundleError(
                            "Encrypted vault bundle changed before restore"
                        )
                    root_descriptor = _open_directory_path_no_follow(
                        destination,
                        label="Disposable encrypted vault restore destination",
                    )
                    try:
                        root_details = os.fstat(root_descriptor)
                        expected_owner = (
                            os.geteuid() if hasattr(os, "geteuid") else root_details.st_uid
                        )
                        if (
                            (root_details.st_dev, root_details.st_ino) != destination_identity
                            or not stat.S_ISDIR(root_details.st_mode)
                            or _mode(root_details) != 0o700
                            or root_details.st_uid != expected_owner
                        ):
                            raise StaffTransportVaultBundleError(
                                "Disposable encrypted vault root changed before restore"
                            )
                        os.lseek(bundle_artifact.descriptor, 0, os.SEEK_SET)
                        with (
                            os.fdopen(
                                os.dup(bundle_artifact.descriptor),
                                "rb",
                                closefd=True,
                            ) as source,
                            zipfile.ZipFile(source, "r") as archive,
                        ):
                            for reference, item in sorted(_expected_references(projection).items()):
                                _restore_member(
                                    root_descriptor,
                                    root_details,
                                    archive,
                                    reference,
                                    item,
                                )
                    finally:
                        os.close(root_descriptor)
                    _recheck_pinned_artifact(
                        bundle_artifact,
                        label="Encrypted vault bundle",
                    )
                finally:
                    bundle_artifact.close()

                restored_analysis = _analyze_vault(
                    projection["inventory"]["objects"],
                    destination,
                )
                _require_exact_analysis(
                    restored_analysis,
                    object_count=projection["inventory"]["uniqueObjectCount"],
                )
                _fsync_restored_vault_tree(destination)
                result = {
                    "format": RESTORE_RECEIPT_FORMAT,
                    "verifiedAt": datetime.now(UTC).isoformat(),
                    "databaseBackup": projection["databaseBackup"],
                    "bundle": bundle_path.name,
                    "bundleSha256": verified["manifest"]["sha256Bundle"],
                    "inventorySha256": projection["inventory"]["sha256"],
                    "restoredObjectCount": projection["inventory"]["uniqueObjectCount"],
                    "ownershipRelationshipCount": projection["inventory"][
                        "ownershipRelationshipCount"
                    ],
                    "databaseVaultConsistencyAuthority": False,
                    "purgeAuthority": False,
                }
                if receipt_path is not None:
                    receipt_identity = _write_private_json_no_clobber(receipt_path, result)
            return result
        except BaseException:
            if receipt_path is not None:
                _unlink_if_identity(receipt_path, receipt_identity)
            _remove_restore_if_identity(destination, destination_identity)
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
    try:
        if args.command == "create":
            bundle, bundle_manifest = create_staff_transport_vault_bundle(
                args.backup,
                args.manifest,
                args.vault_root,
                args.output_directory,
            )
            print(
                "Encrypted staff/transport recovery bundle created and verified "
                f"({bundle.name}, {bundle_manifest.name})"
            )
        elif args.command == "verify":
            result = verify_staff_transport_vault_bundle(
                args.backup,
                args.manifest,
                args.bundle,
                args.bundle_manifest,
            )
            print(
                "Encrypted staff/transport recovery bundle verified "
                f"({result['uniqueObjectCount']} objects)"
            )
        else:
            result = restore_staff_transport_vault_bundle(
                args.backup,
                args.manifest,
                args.bundle,
                args.bundle_manifest,
                args.destination,
                receipt_path=args.receipt,
            )
            print(
                "Disposable encrypted staff/transport vault restored and verified "
                f"({result['restoredObjectCount']} objects)"
            )
    except StaffTransportVaultBundleError as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
