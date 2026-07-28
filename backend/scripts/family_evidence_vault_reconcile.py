"""Create a report-only reconciliation of the private family-evidence vault.

The verified logical database backup is the authority for canonical object
references. Vault traversal and object measurement are descriptor-relative and
never follow symbolic links. Reports contain opaque object keys and integrity
measurements, never evidence content.

This isolated first version intentionally cannot purge. The current backup
contract records ``createdAt`` after snapshot work begins; it does not expose a
verified snapshot-establishment boundary or live-database quiescence proof.
Consequently, absence from one backup cannot authorize deletion. ``--purge``
exists only to fail closed and there is no unlink path for vault content.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Any

from scripts.family_evidence_vault_bundle import (
    EvidenceVaultBundleError,
    derive_evidence_inventory,
)

RECONCILE_FORMAT = "caresync-family-evidence-vault-reconcile-v1"
PURGE_CONFIRMATION = "PURGE CONFIRMED ORPHAN EVIDENCE"
MINIMUM_PURGE_AGE_HOURS = 24 * 30
MAXIMUM_CLOCK_SKEW = timedelta(minutes=5)
MAXIMUM_UNEXPECTED_MEASUREMENT_BYTES = 50 * 1024 * 1024
READ_CHUNK_BYTES = 1024 * 1024
CANONICAL_COMPONENT = re.compile(r"^[0-9a-f]{32}$")
CANONICAL_OBJECT_NAME = re.compile(r"^v1\.(?:pdf|jpg|png)$")


class EvidenceVaultReconcileError(RuntimeError):
    """Raised when vault state is not strong enough for safe reconciliation."""


class _ReferenceIssue(RuntimeError):
    def __init__(self, reason: str, *, indeterminate: bool) -> None:
        super().__init__(reason)
        self.reason = reason
        self.indeterminate = indeterminate


@dataclass(frozen=True)
class _FileRecord:
    reference: str
    device: int
    inode: int
    mode: int
    links: int
    size: int
    modified_ns: int
    changed_ns: int


def _absolute_lexical(path: Path) -> Path:
    return Path(os.path.abspath(path.expanduser()))


def _mode(value: os.stat_result) -> int:
    return stat.S_IMODE(value.st_mode)


def _file_record(reference: str, value: os.stat_result) -> _FileRecord:
    return _FileRecord(
        reference=reference,
        device=value.st_dev,
        inode=value.st_ino,
        mode=_mode(value),
        links=value.st_nlink,
        size=value.st_size,
        modified_ns=value.st_mtime_ns,
        changed_ns=value.st_ctime_ns,
    )


def _stable_stat(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_nlink,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _record_matches(record: _FileRecord, value: os.stat_result) -> bool:
    return (
        record.device,
        record.inode,
        record.mode,
        record.links,
        record.size,
        record.modified_ns,
        record.changed_ns,
    ) == (
        value.st_dev,
        value.st_ino,
        _mode(value),
        value.st_nlink,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _parse_backup_time(value: Any) -> datetime:
    if not isinstance(value, str) or not value:
        raise EvidenceVaultReconcileError("Verified backup has no usable createdAt timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise EvidenceVaultReconcileError(
            "Verified backup createdAt timestamp is invalid"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EvidenceVaultReconcileError(
            "Verified backup createdAt timestamp must include a timezone"
        )
    return parsed.astimezone(UTC)


def _normalize_now(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None or value.utcoffset() is None:
        raise EvidenceVaultReconcileError("Reconciliation time must include a timezone")
    return value.astimezone(UTC)


def _validate_age(minimum_age_hours: int) -> timedelta:
    if (
        isinstance(minimum_age_hours, bool)
        or not isinstance(minimum_age_hours, int)
        or minimum_age_hours < MINIMUM_PURGE_AGE_HOURS
    ):
        raise EvidenceVaultReconcileError(
            f"Minimum purge age cannot be below {MINIMUM_PURGE_AGE_HOURS} hours"
        )
    return timedelta(hours=minimum_age_hours)


def _require_descriptor_primitives() -> None:
    if not hasattr(os, "O_DIRECTORY") or not hasattr(os, "O_NOFOLLOW"):
        raise EvidenceVaultReconcileError(
            "This platform cannot provide descriptor-relative no-follow traversal"
        )
    if (
        os.open not in os.supports_dir_fd
        or os.scandir not in os.supports_fd
        or os.stat not in os.supports_dir_fd
        or os.unlink not in os.supports_dir_fd
    ):
        raise EvidenceVaultReconcileError(
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


def _open_directory_path_no_follow(path: Path, *, label: str) -> int:
    """Open an absolute directory one component at a time without symlinks."""

    absolute = _absolute_lexical(path)
    current = os.open(absolute.anchor, _directory_flags())
    try:
        for part in absolute.parts[1:]:
            child = os.open(part, _directory_flags(), dir_fd=current)
            os.close(current)
            current = child
        return current
    except FileNotFoundError:
        os.close(current)
        raise
    except OSError as error:
        os.close(current)
        raise EvidenceVaultReconcileError(
            f"{label} contains a symbolic-link component or non-directory component"
        ) from error


def _canonical_reference(reference: str) -> bool:
    parts = PurePosixPath(reference).parts
    return (
        len(parts) == 4
        and all(CANONICAL_COMPONENT.fullmatch(part) for part in parts[:3])
        and CANONICAL_OBJECT_NAME.fullmatch(parts[3]) is not None
        and "\\" not in reference
        and "\x00" not in reference
    )


def _prefixes(reference: str) -> set[str]:
    parts = PurePosixPath(reference).parts
    return {"/".join(parts[:index]) for index in range(1, len(parts))}


def _enumerate_from_descriptor(
    root_descriptor: int,
    root_details: os.stat_result,
) -> tuple[
    dict[str, _FileRecord],
    dict[str, _FileRecord],
    list[dict[str, str]],
    list[dict[str, str]],
]:
    files: dict[str, _FileRecord] = {}
    directories: dict[str, _FileRecord] = {}
    unsafe: list[dict[str, str]] = []
    indeterminate: list[dict[str, str]] = []

    def walk(
        directory_descriptor: int,
        relative: PurePosixPath,
        opened_details: os.stat_result,
    ) -> None:
        try:
            with os.scandir(directory_descriptor) as iterator:
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
                indeterminate.append(
                    {"reference": reference, "reason": "entry_unreadable"}
                )
                continue
            if stat.S_ISLNK(details.st_mode):
                unsafe.append({"reference": reference, "reason": "symbolic_link"})
                continue
            if stat.S_ISDIR(details.st_mode):
                record = _file_record(reference, details)
                directories[reference] = record
                if _mode(details) != 0o700:
                    unsafe.append(
                        {"reference": reference, "reason": "directory_mode_not_0700"}
                    )
                    continue
                if details.st_dev != root_details.st_dev:
                    unsafe.append(
                        {"reference": reference, "reason": "cross_device_directory"}
                    )
                    continue
                try:
                    child_descriptor = os.open(
                        entry.name,
                        _directory_flags(),
                        dir_fd=directory_descriptor,
                    )
                except OSError:
                    indeterminate.append(
                        {
                            "reference": reference,
                            "reason": "directory_changed_before_open",
                        }
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
                files[reference] = _file_record(reference, details)
                if _mode(details) != 0o600:
                    unsafe.append(
                        {"reference": reference, "reason": "file_mode_not_0600"}
                    )
                if details.st_nlink != 1:
                    unsafe.append(
                        {"reference": reference, "reason": "file_link_count_not_one"}
                    )
                continue
            unsafe.append({"reference": reference, "reason": "special_file"})
        try:
            after = os.fstat(directory_descriptor)
        except OSError:
            indeterminate.append(
                {"reference": relative.as_posix(), "reason": "directory_became_unreadable"}
            )
            return
        if _stable_stat(after) != _stable_stat(opened_details):
            indeterminate.append(
                {"reference": relative.as_posix(), "reason": "directory_changed_during_scan"}
            )

    walk(root_descriptor, PurePosixPath(), root_details)
    return files, directories, unsafe, indeterminate


def _measurement(record: _FileRecord, digest: str | None) -> dict[str, Any]:
    return {
        "device": record.device,
        "inode": record.inode,
        "mode": f"{record.mode:04o}",
        "linkCount": record.links,
        "byteSize": record.size,
        "modifiedNs": record.modified_ns,
        "changedNs": record.changed_ns,
        "contentSha256": digest,
    }


def _measure_reference(
    root_descriptor: int,
    root_details: os.stat_result,
    reference: str,
    *,
    file_record: _FileRecord,
    directory_records: dict[str, _FileRecord],
    maximum_bytes: int,
    include_digest: bool = True,
) -> dict[str, Any]:
    """Hash one enumerated leaf while holding and rechecking its descriptor chain."""

    if not _canonical_reference(reference):
        raise _ReferenceIssue("noncanonical_reference", indeterminate=False)
    parts = PurePosixPath(reference).parts
    descriptors: list[tuple[int, os.stat_result]] = []
    file_descriptor: int | None = None
    current = root_descriptor
    try:
        root_before = os.fstat(root_descriptor)
        if _stable_stat(root_before) != _stable_stat(root_details):
            raise _ReferenceIssue("vault_changed_after_scan", indeterminate=True)
        for index, part in enumerate(parts[:-1], start=1):
            prefix = "/".join(parts[:index])
            expected_directory = directory_records.get(prefix)
            if expected_directory is None:
                raise _ReferenceIssue("directory_changed_after_scan", indeterminate=True)
            try:
                child = os.open(part, _directory_flags(), dir_fd=current)
            except OSError as error:
                raise _ReferenceIssue(
                    "directory_changed_after_scan", indeterminate=True
                ) from error
            details = os.fstat(child)
            if (
                not _record_matches(expected_directory, details)
                or not stat.S_ISDIR(details.st_mode)
                or _mode(details) != 0o700
                or details.st_dev != root_details.st_dev
            ):
                os.close(child)
                raise _ReferenceIssue("directory_changed_after_scan", indeterminate=True)
            descriptors.append((child, details))
            current = child
        try:
            file_descriptor = os.open(parts[-1], _file_flags(), dir_fd=current)
        except OSError as error:
            raise _ReferenceIssue("file_changed_after_scan", indeterminate=True) from error
        before = os.fstat(file_descriptor)
        if not _record_matches(file_record, before):
            raise _ReferenceIssue("file_changed_after_scan", indeterminate=True)
        if (
            not stat.S_ISREG(before.st_mode)
            or _mode(before) != 0o600
            or before.st_nlink != 1
            or before.st_dev != root_details.st_dev
        ):
            raise _ReferenceIssue("unsafe_leaf", indeterminate=False)
        if include_digest and before.st_size > maximum_bytes:
            raise _ReferenceIssue("measurement_limit_exceeded", indeterminate=True)

        digest = hashlib.sha256() if include_digest else None
        total = 0
        if digest is not None:
            while True:
                chunk = os.read(file_descriptor, READ_CHUNK_BYTES)
                if not chunk:
                    break
                total += len(chunk)
                if total > maximum_bytes:
                    raise _ReferenceIssue(
                        "measurement_limit_exceeded", indeterminate=True
                    )
                digest.update(chunk)
        after = os.fstat(file_descriptor)
        if (
            (digest is not None and total != before.st_size)
            or _stable_stat(after) != _stable_stat(before)
        ):
            raise _ReferenceIssue("concurrent_file_change", indeterminate=True)
        for descriptor, opened in descriptors:
            if _stable_stat(os.fstat(descriptor)) != _stable_stat(opened):
                raise _ReferenceIssue("concurrent_directory_change", indeterminate=True)
        if _stable_stat(os.fstat(root_descriptor)) != _stable_stat(root_before):
            raise _ReferenceIssue("concurrent_vault_change", indeterminate=True)
        return _measurement(
            file_record,
            digest.hexdigest() if digest is not None else None,
        )
    except OSError as error:
        raise _ReferenceIssue("measurement_io_error", indeterminate=True) from error
    finally:
        if file_descriptor is not None:
            os.close(file_descriptor)
        for descriptor, _ in reversed(descriptors):
            os.close(descriptor)


def _settled_before_boundaries(
    measurement: dict[str, Any],
    *,
    backup_time: datetime,
    now: datetime,
    minimum_age: timedelta,
) -> bool:
    latest_change = datetime.fromtimestamp(
        max(measurement["modifiedNs"], measurement["changedNs"]) / 1_000_000_000,
        tz=UTC,
    )
    return (
        latest_change <= backup_time - minimum_age
        and latest_change <= now - minimum_age
    )


def _deduplicate_findings(values: list[dict[str, str]]) -> list[dict[str, str]]:
    unique = {(value["reference"], value["reason"]) for value in values}
    return [
        {"reference": reference, "reason": reason}
        for reference, reason in sorted(unique)
    ]


def _absent_analysis(expected: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        "expectedCount": len(expected),
        "presentCount": 0,
        "missing": sorted(expected),
        "mismatched": [],
        "unexpected": [],
        "unsafe": [{"reference": ".", "reason": "vault_root_absent"}],
        "indeterminate": [],
        "unclassifiedDirectories": [],
        "vaultIdentity": None,
    }


def _analyze(
    *,
    inventory: list[dict[str, Any]],
    backup_time: datetime,
    vault_root: Path,
    now: datetime,
    minimum_age: timedelta,
) -> dict[str, Any]:
    expected = {item["storageReference"]: item for item in inventory}
    root = _absolute_lexical(vault_root)
    try:
        root_descriptor = _open_directory_path_no_follow(
            root,
            label="Evidence vault root",
        )
    except FileNotFoundError:
        return _absent_analysis(expected)
    try:
        root_details = os.fstat(root_descriptor)
        if not stat.S_ISDIR(root_details.st_mode) or _mode(root_details) != 0o700:
            raise EvidenceVaultReconcileError(
                "Evidence vault root must be a mode 0700 directory"
            )
        files, directories, unsafe, indeterminate = _enumerate_from_descriptor(
            root_descriptor,
            root_details,
        )
        missing: list[str] = []
        mismatched: list[dict[str, str]] = []
        present: list[str] = []
        for reference, item in sorted(expected.items()):
            record = files.get(reference)
            if record is None:
                missing.append(reference)
                continue
            size_mismatch = record.size != item["byteSize"]
            try:
                measured = _measure_reference(
                    root_descriptor,
                    root_details,
                    reference,
                    file_record=record,
                    directory_records=directories,
                    maximum_bytes=item["byteSize"],
                    include_digest=not size_mismatch,
                )
            except _ReferenceIssue as error:
                if error.indeterminate:
                    indeterminate.append(
                        {"reference": reference, "reason": error.reason}
                    )
                else:
                    mismatched.append(
                        {"reference": reference, "reason": "unsafe_or_unreadable"}
                    )
                continue
            if size_mismatch or measured["byteSize"] != item["byteSize"]:
                mismatched.append(
                    {"reference": reference, "reason": "byte_size_mismatch"}
                )
            elif measured["contentSha256"] != item["contentSha256"]:
                mismatched.append(
                    {"reference": reference, "reason": "content_sha256_mismatch"}
                )
            else:
                present.append(reference)

        unexpected_records = {
            reference: record
            for reference, record in files.items()
            if reference not in expected
        }
        unexpected: list[dict[str, Any]] = []
        candidate_prefixes: set[str] = set()
        directory_names = set(directories)
        for reference, record in sorted(unexpected_records.items()):
            reasons: list[str] = []
            canonical = _canonical_reference(reference)
            measured: dict[str, Any] | None = None
            classification = "unsafe_unexpected"
            if not canonical:
                reasons.append("noncanonical_reference")
            if record.mode != 0o600:
                reasons.append("file_mode_not_0600")
            if record.links != 1:
                reasons.append("file_link_count_not_one")
            object_prefix = reference.rsplit("/", 1)[0]
            siblings = [
                value for value in files if value.rsplit("/", 1)[0] == object_prefix
            ]
            child_directories = [
                value for value in directory_names if value.startswith(object_prefix + "/")
            ]
            if len(siblings) != 1 or child_directories:
                reasons.append("object_directory_not_exclusive")
            if canonical:
                candidate_prefixes.update(_prefixes(reference))
            if canonical and not reasons:
                try:
                    measured = _measure_reference(
                        root_descriptor,
                        root_details,
                        reference,
                        file_record=record,
                        directory_records=directories,
                        maximum_bytes=MAXIMUM_UNEXPECTED_MEASUREMENT_BYTES,
                    )
                except _ReferenceIssue as error:
                    reasons.append(error.reason)
                    if error.indeterminate:
                        classification = "indeterminate"
                        indeterminate.append(
                            {"reference": reference, "reason": error.reason}
                        )
                else:
                    classification = "unexpected_candidate"
                    if not _settled_before_boundaries(
                        measured,
                        backup_time=backup_time,
                        now=now,
                        minimum_age=minimum_age,
                    ):
                        reasons.append("not_old_enough_before_backup_and_now")
            historical_candidate = (
                classification == "unexpected_candidate" and not reasons
            )
            unexpected.append(
                {
                    "reference": reference,
                    "classification": classification,
                    "canonical": canonical,
                    "firstObservedAt": now.isoformat(),
                    "historicalCandidate": historical_candidate,
                    "purgeEligible": False,
                    "reasons": reasons,
                    "measurement": measured,
                }
            )

        expected_prefixes = (
            set().union(*(_prefixes(value) for value in expected)) if expected else set()
        )
        allowed_directories = expected_prefixes | candidate_prefixes
        unclassified_directories = sorted(directory_names - allowed_directories)

        try:
            reopened = _open_directory_path_no_follow(
                root,
                label="Evidence vault root",
            )
        except (FileNotFoundError, EvidenceVaultReconcileError):
            indeterminate.append(
                {"reference": ".", "reason": "vault_root_path_changed"}
            )
        else:
            try:
                reopened_details = os.fstat(reopened)
                if (
                    reopened_details.st_dev,
                    reopened_details.st_ino,
                ) != (root_details.st_dev, root_details.st_ino):
                    indeterminate.append(
                        {"reference": ".", "reason": "vault_root_path_changed"}
                    )
            finally:
                os.close(reopened)

        if indeterminate:
            for item in unexpected:
                if item["classification"] == "unexpected_candidate":
                    item["classification"] = "indeterminate"
                    item["historicalCandidate"] = False
                    if "vault_scan_indeterminate" not in item["reasons"]:
                        item["reasons"].append("vault_scan_indeterminate")

        return {
            "expectedCount": len(expected),
            "presentCount": len(present),
            "missing": sorted(missing),
            "mismatched": mismatched,
            "unexpected": unexpected,
            "unsafe": _deduplicate_findings(unsafe),
            "indeterminate": _deduplicate_findings(indeterminate),
            "unclassifiedDirectories": unclassified_directories,
            "vaultIdentity": {
                "device": root_details.st_dev,
                "inode": root_details.st_ino,
                "mode": f"{_mode(root_details):04o}",
                "modifiedNs": root_details.st_mtime_ns,
                "changedNs": root_details.st_ctime_ns,
            },
        }
    finally:
        os.close(root_descriptor)


def reconcile_evidence_vault(
    backup_path: Path,
    manifest_path: Path,
    vault_root: Path,
    *,
    purge: bool = False,
    confirmation: str | None = None,
    minimum_age_hours: int = MINIMUM_PURGE_AGE_HOURS,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return an integrity report; every purge request fails closed."""

    if confirmation is not None and not purge:
        raise EvidenceVaultReconcileError("Purge confirmation is invalid without purge")
    minimum_age = _validate_age(minimum_age_hours)
    observed_now = _normalize_now(now)
    try:
        verified, inventory = derive_evidence_inventory(backup_path, manifest_path)
    except EvidenceVaultBundleError as error:
        raise EvidenceVaultReconcileError(str(error)) from error
    backup_time = _parse_backup_time(verified["header"].get("createdAt"))
    if backup_time > observed_now + MAXIMUM_CLOCK_SKEW:
        raise EvidenceVaultReconcileError("Verified backup createdAt is in the future")

    analysis = _analyze(
        inventory=inventory,
        backup_time=backup_time,
        vault_root=vault_root,
        now=observed_now,
        minimum_age=minimum_age,
    )
    historical_candidates = [
        item["reference"]
        for item in analysis["unexpected"]
        if item["historicalCandidate"]
    ]
    blockers: list[str] = [
        "backup_contract_has_no_snapshot_established_boundary",
        "live_database_quiescence_unproven",
    ]
    if not inventory:
        blockers.append("empty_backup_inventory_cannot_anchor_vault_identity")
    if analysis["missing"]:
        blockers.append("expected_objects_missing")
    if analysis["mismatched"]:
        blockers.append("expected_objects_mismatched")
    if analysis["unsafe"]:
        blockers.append("unsafe_vault_entries_present")
    if analysis["indeterminate"]:
        blockers.append("indeterminate_vault_state")
    if analysis["unclassifiedDirectories"]:
        blockers.append("unclassified_directories_present")
    if any(not item["canonical"] for item in analysis["unexpected"]):
        blockers.append("noncanonical_unexpected_files_present")

    if purge:
        if confirmation != PURGE_CONFIRMATION:
            raise EvidenceVaultReconcileError(
                f"Purge requires exact confirmation: {PURGE_CONFIRMATION}"
            )
        raise EvidenceVaultReconcileError(
            "Purge is unavailable in the report-only reconciler: "
            "the verified backup contract has no snapshotEstablishedAt boundary "
            "and no live-database quiescence proof"
        )

    return {
        "format": RECONCILE_FORMAT,
        "mode": "report",
        "generatedAt": observed_now.isoformat(),
        "backup": {
            "createdAt": backup_time.isoformat(),
            "sha256Compressed": verified["manifest"].get("sha256Compressed"),
            "sha256Rows": verified["manifest"].get("sha256Rows"),
            "alembicRevisions": verified["header"].get("alembicRevisions", []),
        },
        "vaultRoot": os.fspath(_absolute_lexical(vault_root)),
        **analysis,
        "purge": {
            "available": False,
            "requested": False,
            "confirmationPhrase": PURGE_CONFIRMATION,
            "minimumAgeHours": minimum_age_hours,
            "historicalCandidateReferences": sorted(historical_candidates),
            "eligibleReferences": [],
            "blockedReasons": blockers,
            "purgedReferences": [],
        },
    }


def write_reconcile_report(path: Path, payload: dict[str, Any]) -> None:
    """Write a durable, mode-0600 JSON report without replacing any artifact."""

    absolute = _absolute_lexical(path)
    if absolute.name in {"", ".", ".."}:
        raise EvidenceVaultReconcileError("Reconciliation output path is invalid")
    serialized = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    try:
        parent_descriptor = _open_directory_path_no_follow(
            absolute.parent,
            label="Reconciliation output parent",
        )
    except FileNotFoundError as error:
        raise EvidenceVaultReconcileError(
            "Reconciliation output parent is absent"
        ) from error
    created = False
    try:
        parent_details = os.fstat(parent_descriptor)
        if not stat.S_ISDIR(parent_details.st_mode) or _mode(parent_details) != 0o700:
            raise EvidenceVaultReconcileError(
                "Reconciliation output parent must be a mode 0700 directory"
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
            raise EvidenceVaultReconcileError(
                f"Refusing to replace existing reconciliation report {absolute}"
            ) from error
        except OSError as error:
            raise EvidenceVaultReconcileError(
                "Reconciliation report could not be created safely"
            ) from error
        created = True
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb", closefd=True) as destination:
                destination.write(serialized)
                destination.flush()
                os.fsync(destination.fileno())
            report_details = os.stat(
                absolute.name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
            if (
                not stat.S_ISREG(report_details.st_mode)
                or _mode(report_details) != 0o600
                or report_details.st_nlink != 1
            ):
                raise EvidenceVaultReconcileError(
                    "Reconciliation report did not remain a private single-link file"
                )
            os.fsync(parent_descriptor)
        except BaseException:
            try:
                os.unlink(absolute.name, dir_fd=parent_descriptor)
                os.fsync(parent_descriptor)
            except OSError:
                pass
            raise
    finally:
        os.close(parent_descriptor)
    if not created:
        raise EvidenceVaultReconcileError("Reconciliation report was not created")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--vault-root", type=Path, required=True)
    output = parser.add_mutually_exclusive_group(required=True)
    output.add_argument("--output", type=Path)
    output.add_argument(
        "--stdout",
        action="store_true",
        help="explicitly emit the opaque-key integrity report to standard output",
    )
    parser.add_argument(
        "--minimum-age-hours",
        type=int,
        default=MINIMUM_PURGE_AGE_HOURS,
    )
    parser.add_argument("--purge", action="store_true")
    parser.add_argument("--confirm-purge")
    args = parser.parse_args()
    if args.confirm_purge is not None and not args.purge:
        parser.error("--confirm-purge is valid only with --purge")
    try:
        result = reconcile_evidence_vault(
            args.backup,
            args.manifest,
            args.vault_root,
            purge=args.purge,
            confirmation=args.confirm_purge,
            minimum_age_hours=args.minimum_age_hours,
        )
        if args.stdout:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            write_reconcile_report(args.output, result)
            print(f"Reconciliation report written: {_absolute_lexical(args.output)}")
    except EvidenceVaultReconcileError as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
