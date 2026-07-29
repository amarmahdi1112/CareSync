"""Fail-closed evidence contract for the CareSync Basic 0039 -> 0043 release.

The release has durable, independently reopenable decisions:

* a *candidate* receipt proves that an exact 0039 source was backed up,
  restored into a different PostgreSQL cluster, migrated to 0043, and
  certified without changing any pre-existing business row; and
* a *commit* receipt proves that the same retained PostgreSQL identity reached
  the already-certified 0043 state.
* a *finalization* receipt is issued only after the committed runtime and the
  fixed loopback API/frontend health surfaces pass while the release fence is
  still present; and
* an explicit 0039 *resume authorization* can be issued instead, but only while
  the retained database is still byte-evidence-equivalent to the captured
  source.

This module deliberately does not stop processes, revoke logins, run Alembic,
restore a database, or copy vault bytes.  The launcher owns those actions.  It
calls this module at the boundaries, and this module makes those actions
cryptographically and structurally attributable to one release.

Receipts contain no connection URLs, passwords, keys, or artifact contents.
They bind owner-only artifacts by SHA-256, byte length, and basename only.
All receipt writes use a durable temporary file plus atomic no-replace
publication, reject symbolic-link path components, and verify that the
resulting file has exactly one hard link.
"""

from __future__ import annotations

import argparse
import ctypes
import errno
import hashlib
import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

if __package__:
    from .darwin_durability import full_sync_fd
else:
    from darwin_durability import full_sync_fd

SOURCE_REVISION = "0039_admissions_decision_spine"
INTERMEDIATE_REVISION = "0042_billing_policy_recert"
TARGET_REVISION = "0043_org_wide_room_presence"

NEW_0041_TABLES = (
    "room_operational_exception_events",
    "room_operational_exception_heads",
    "staff_room_presence_events",
    "staff_room_presence_sessions",
)

CLONE_CERTIFICATE_FORMAT = "caresync-release-clone-certificate-v1"
RELEASE_PAYLOAD_FORMAT = "caresync-basic-release-payload-v1"
CANDIDATE_RECEIPT_FORMAT = "caresync-basic-release-candidate-v1"
COMMIT_RECEIPT_FORMAT = "caresync-basic-release-commit-v1"
RESUME_AUTHORIZATION_FORMAT = "caresync-basic-release-resume-0039-v1"
FINALIZATION_RECEIPT_FORMAT = "caresync-basic-release-finalization-v1"
PHYSICAL_REHEARSAL_RECEIPT_FORMAT = (
    "caresync-basic-physical-backup-rehearsal-v1"
)
PHYSICAL_REHEARSAL_OBSERVATION_FORMAT = (
    "caresync-basic-physical-backup-observation-v1"
)
PHYSICAL_BACKUP_INVENTORY_FORMAT = "caresync-basic-physical-backup-inventory-v2"

CORE_ARTIFACTS = frozenset(
    {
        "backup",
        "backup_manifest",
        "database_restore_receipt",
        "physical_backup_manifest",
        "physical_backup_inventory",
        "physical_rehearsal_observation",
        "physical_rehearsal_receipt",
        "prepared_fence_context",
        "release_probe_credential",
        "release_source_manifest",
        "retained_identity",
    }
)
FAMILY_VAULT_ARTIFACTS = frozenset(
    {
        "family_vault_bundle",
        "family_vault_manifest",
        "family_vault_restore_receipt",
    }
)
STAFF_TRANSPORT_VAULT_ARTIFACTS = frozenset(
    {
        "staff_transport_vault_bundle",
        "staff_transport_vault_manifest",
        "staff_transport_vault_restore_receipt",
        "staff_transport_vault_key",
    }
)
CALLER_ARTIFACTS = (
    CORE_ARTIFACTS | FAMILY_VAULT_ARTIFACTS | STAFF_TRANSPORT_VAULT_ARTIFACTS
)
GENERATED_ARTIFACTS = frozenset({"clone_certificate", "release_payload"})

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SAFE_ARTIFACT_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,254}$")
_SUSPICIOUS_SECRET_TEXT = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)\b(?:postgres(?:ql)?|mysql|mariadb)://[^/\s:@]+:[^@\s]+@"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
)
_MAX_JSON_BYTES = 16 * 1024 * 1024

ArtifactBinding = dict[str, Any]
Snapshot = dict[str, Any]
RuntimeCertificateHook = Callable[[Any], None]


class ReleaseContractError(RuntimeError):
    """Raised when release evidence is incomplete, inconsistent, or unsafe."""


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _absolute_lexical(path: Path) -> Path:
    return Path(os.path.abspath(path.expanduser()))


def _assert_no_symlink_components(path: Path) -> None:
    absolute = _absolute_lexical(path)
    cursor = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        cursor = cursor / part
        if os.path.lexists(cursor) and stat.S_ISLNK(cursor.lstat().st_mode):
            raise ReleaseContractError(
                f"Private release path {path} contains a symbolic link"
            )


def _open_directory_no_follow(path: Path) -> int:
    absolute = _absolute_lexical(path)
    if not hasattr(os, "O_DIRECTORY") or not hasattr(os, "O_NOFOLLOW"):
        raise ReleaseContractError(
            "This platform cannot enforce private release receipt creation"
        )
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    descriptor = os.open(absolute.anchor, flags)
    try:
        for part in absolute.parts[1:]:
            child = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor
    except OSError as error:
        os.close(descriptor)
        raise ReleaseContractError(
            "Private release path contains an unsafe directory component"
        ) from error


def _owner_private_directory(path: Path) -> bool:
    try:
        details = path.lstat()
    except OSError:
        return False
    return bool(
        stat.S_ISDIR(details.st_mode)
        and stat.S_IMODE(details.st_mode) == 0o700
        and details.st_uid == os.geteuid()
    )


def _barrier_private_directory_entry(path: Path) -> None:
    """Durably publish one private directory and its parent entry."""

    _assert_no_symlink_components(path)
    expected = path.lstat()
    parent_expected = path.parent.lstat()
    if (
        not stat.S_ISDIR(expected.st_mode)
        or stat.S_IMODE(expected.st_mode) != 0o700
        or expected.st_uid != os.geteuid()
        or not stat.S_ISDIR(parent_expected.st_mode)
    ):
        raise ReleaseContractError(
            "Release receipt parent must be an owner-controlled mode 0700 directory"
        )
    directory_descriptor = _open_directory_no_follow(path)
    parent_descriptor = _open_directory_no_follow(path.parent)
    try:
        opened = os.fstat(directory_descriptor)
        parent_opened = os.fstat(parent_descriptor)
        if (
            (opened.st_dev, opened.st_ino)
            != (expected.st_dev, expected.st_ino)
            or (parent_opened.st_dev, parent_opened.st_ino)
            != (parent_expected.st_dev, parent_expected.st_ino)
        ):
            raise ReleaseContractError(
                "Release receipt parent changed before its durability barrier"
            )
        full_sync_fd(directory_descriptor)
        full_sync_fd(parent_descriptor)
        finished = os.fstat(directory_descriptor)
        parent_finished = os.fstat(parent_descriptor)
        reopened = path.lstat()
        parent_reopened = path.parent.lstat()
        stable_fields = ("st_dev", "st_ino", "st_mode", "st_uid")
        if (
            any(
                getattr(opened, field) != getattr(finished, field)
                or getattr(finished, field) != getattr(reopened, field)
                for field in stable_fields
            )
            or any(
                getattr(parent_opened, field)
                != getattr(parent_finished, field)
                or getattr(parent_finished, field)
                != getattr(parent_reopened, field)
                for field in stable_fields
            )
        ):
            raise ReleaseContractError(
                "Release receipt parent changed during its durability barrier"
            )
    finally:
        os.close(directory_descriptor)
        os.close(parent_descriptor)


def _ensure_private_directory(path: Path) -> Path:
    absolute = _absolute_lexical(path)
    _assert_no_symlink_components(absolute)
    if os.path.lexists(absolute):
        details = absolute.lstat()
        if not stat.S_ISDIR(details.st_mode):
            raise ReleaseContractError("Release receipt parent is not a directory")
        if not _owner_private_directory(absolute):
            raise ReleaseContractError(
                "Release receipt parent must be an owner-controlled mode 0700 directory"
            )
        # An earlier process may have lost power or returned after either
        # durability barrier failed. Reissue both barriers even when the
        # directory is already present; existence is not durability proof.
        _barrier_private_directory_entry(absolute)
    else:
        missing: list[Path] = []
        cursor = absolute
        while not os.path.lexists(cursor):
            missing.append(cursor)
            if cursor.parent == cursor:
                raise ReleaseContractError(
                    "Release receipt parent has no existing ancestor"
                )
            cursor = cursor.parent
        if cursor.is_symlink() or not cursor.is_dir():
            raise ReleaseContractError(
                "Release receipt parent has an unsafe existing ancestor"
            )
        # If a prior attempt stopped after creating an outer component but
        # before its parent barrier completed, the deepest existing private
        # ancestor is the retry boundary. Re-barrier it before creating any
        # deeper component.
        if _owner_private_directory(cursor):
            _barrier_private_directory_entry(cursor)
        for directory in reversed(missing):
            try:
                directory.mkdir(mode=0o700)
            except FileExistsError as error:
                raise ReleaseContractError(
                    "Release receipt parent changed while it was created"
                ) from error
            directory.chmod(0o700)
            _barrier_private_directory_entry(directory)
    details = absolute.lstat()
    if (
        not stat.S_ISDIR(details.st_mode)
        or stat.S_IMODE(details.st_mode) != 0o700
        or details.st_uid != os.geteuid()
    ):
        raise ReleaseContractError(
            "Release receipt parent must be an owner-controlled mode 0700 directory"
        )
    return absolute


def _assert_private_regular_file(path: Path, *, label: str) -> Path:
    absolute = _absolute_lexical(path)
    _assert_no_symlink_components(absolute)
    try:
        details = absolute.lstat()
    except FileNotFoundError as error:
        raise ReleaseContractError(f"{label} does not exist") from error
    if (
        not stat.S_ISREG(details.st_mode)
        or stat.S_IMODE(details.st_mode) != 0o600
        or details.st_uid != os.geteuid()
        or details.st_nlink != 1
    ):
        raise ReleaseContractError(
            f"{label} must be an owner-controlled mode 0600 single-link file"
        )
    parent = absolute.parent.lstat()
    if (
        not stat.S_ISDIR(parent.st_mode)
        or stat.S_IMODE(parent.st_mode) != 0o700
        or parent.st_uid != os.geteuid()
    ):
        raise ReleaseContractError(
            f"{label} parent must be an owner-controlled mode 0700 directory"
        )
    return absolute


def _publish_file_no_replace(source: Path, destination: Path) -> None:
    """Atomically rename ``source`` to an absent ``destination``."""

    libc = ctypes.CDLL(None, use_errno=True)
    source_bytes = os.fsencode(source)
    destination_bytes = os.fsencode(destination)
    if sys.platform == "darwin":
        renamex_np = libc.renamex_np
        renamex_np.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        renamex_np.restype = ctypes.c_int
        result = renamex_np(source_bytes, destination_bytes, 0x00000004)
    elif hasattr(libc, "renameat2"):
        renameat2 = libc.renameat2
        renameat2.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        renameat2.restype = ctypes.c_int
        result = renameat2(-100, source_bytes, -100, destination_bytes, 1)
    else:
        raise ReleaseContractError(
            "Atomic no-replace receipt publication is unavailable"
        )
    if result != 0:
        error_number = ctypes.get_errno()
        if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
            raise ReleaseContractError(
                f"Refusing to replace existing release receipt {destination}"
            )
        raise ReleaseContractError(
            "Release receipt could not be atomically published"
        ) from OSError(error_number, os.strerror(error_number))


def atomic_rename_no_replace(source: Path, destination: Path) -> None:
    """Atomically move one owner-controlled path without replacing anything."""

    source_absolute = _absolute_lexical(source)
    destination_absolute = _absolute_lexical(destination)
    _assert_no_symlink_components(source_absolute)
    _assert_no_symlink_components(destination_absolute.parent)
    try:
        source_details = source_absolute.lstat()
        source_parent = source_absolute.parent.lstat()
        destination_parent = destination_absolute.parent.lstat()
    except OSError as error:
        raise ReleaseContractError("Atomic rename paths are incomplete") from error
    if (
        stat.S_ISLNK(source_details.st_mode)
        or source_details.st_uid != os.geteuid()
        or not stat.S_ISDIR(source_parent.st_mode)
        or not stat.S_ISDIR(destination_parent.st_mode)
        or source_parent.st_uid != os.geteuid()
        or destination_parent.st_uid != os.geteuid()
        or stat.S_IMODE(source_parent.st_mode) != 0o700
        or stat.S_IMODE(destination_parent.st_mode) != 0o700
        or source_details.st_dev != destination_parent.st_dev
        or os.path.lexists(destination_absolute)
    ):
        raise ReleaseContractError(
            "Atomic rename requires an absent destination on one private filesystem"
        )
    source_parent_descriptor = _open_directory_no_follow(source_absolute.parent)
    destination_parent_descriptor = _open_directory_no_follow(
        destination_absolute.parent
    )
    try:
        _publish_file_no_replace(source_absolute, destination_absolute)
        moved = destination_absolute.lstat()
        if (
            moved.st_uid != os.geteuid()
            or (moved.st_dev, moved.st_ino)
            != (source_details.st_dev, source_details.st_ino)
            or os.path.lexists(source_absolute)
        ):
            raise ReleaseContractError("Atomic rename postconditions failed")
        full_sync_fd(source_parent_descriptor)
        if destination_parent_descriptor != source_parent_descriptor:
            full_sync_fd(destination_parent_descriptor)
    finally:
        os.close(source_parent_descriptor)
        os.close(destination_parent_descriptor)


def durable_publish_private_file(
    source: Path,
    destination: Path,
    *,
    replace_existing: bool = False,
) -> None:
    """Fsync and atomically publish one private file, optionally replacing one."""

    source_absolute = _absolute_lexical(source)
    destination_absolute = _absolute_lexical(destination)
    _assert_no_symlink_components(source_absolute)
    _assert_no_symlink_components(destination_absolute.parent)
    try:
        source_details = source_absolute.lstat()
        source_parent_details = source_absolute.parent.lstat()
        destination_parent_details = destination_absolute.parent.lstat()
    except OSError as error:
        raise ReleaseContractError(
            "Durable private-file publication paths are incomplete"
        ) from error
    if (
        not stat.S_ISREG(source_details.st_mode)
        or stat.S_IMODE(source_details.st_mode) != 0o600
        or source_details.st_uid != os.geteuid()
        or source_details.st_nlink != 1
        or not stat.S_ISDIR(source_parent_details.st_mode)
        or not stat.S_ISDIR(destination_parent_details.st_mode)
        or stat.S_IMODE(source_parent_details.st_mode) != 0o700
        or stat.S_IMODE(destination_parent_details.st_mode) != 0o700
        or source_parent_details.st_uid != os.geteuid()
        or destination_parent_details.st_uid != os.geteuid()
        or source_details.st_dev != destination_parent_details.st_dev
    ):
        raise ReleaseContractError(
            "Durable publication requires one private single-link source file"
        )
    destination_exists = os.path.lexists(destination_absolute)
    if replace_existing:
        if not destination_exists:
            raise ReleaseContractError(
                "Durable replacement requires an existing private destination"
            )
        destination_details = destination_absolute.lstat()
        if (
            not stat.S_ISREG(destination_details.st_mode)
            or stat.S_IMODE(destination_details.st_mode) != 0o600
            or destination_details.st_uid != os.geteuid()
            or destination_details.st_nlink != 1
            or destination_details.st_dev != source_details.st_dev
        ):
            raise ReleaseContractError(
                "Durable replacement destination is not a private file"
            )
    elif destination_exists:
        raise ReleaseContractError(
            f"Refusing to replace existing release receipt {destination_absolute}"
        )

    source_parent_descriptor = _open_directory_no_follow(source_absolute.parent)
    destination_parent_descriptor = _open_directory_no_follow(
        destination_absolute.parent
    )
    source_flags = os.O_RDONLY | os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        source_flags |= os.O_CLOEXEC
    source_descriptor = os.open(
        source_absolute.name,
        source_flags,
        dir_fd=source_parent_descriptor,
    )
    try:
        opened = os.fstat(source_descriptor)
        if (opened.st_dev, opened.st_ino) != (
            source_details.st_dev,
            source_details.st_ino,
        ):
            raise ReleaseContractError(
                "Durable private-file source changed before publication"
            )
        full_sync_fd(source_descriptor)
        full_sync_fd(source_parent_descriptor)
        if replace_existing:
            current_destination = os.stat(
                destination_absolute.name,
                dir_fd=destination_parent_descriptor,
                follow_symlinks=False,
            )
            if (current_destination.st_dev, current_destination.st_ino) != (
                destination_details.st_dev,
                destination_details.st_ino,
            ):
                raise ReleaseContractError(
                    "Durable replacement destination changed before publication"
                )
            os.replace(
                source_absolute.name,
                destination_absolute.name,
                src_dir_fd=source_parent_descriptor,
                dst_dir_fd=destination_parent_descriptor,
            )
        else:
            _publish_file_no_replace(source_absolute, destination_absolute)
        published = os.stat(
            destination_absolute.name,
            dir_fd=destination_parent_descriptor,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISREG(published.st_mode)
            or stat.S_IMODE(published.st_mode) != 0o600
            or published.st_uid != os.geteuid()
            or published.st_nlink != 1
            or (published.st_dev, published.st_ino)
            != (source_details.st_dev, source_details.st_ino)
            or os.path.lexists(source_absolute)
        ):
            raise ReleaseContractError(
                "Durable private-file publication postconditions failed"
            )
        full_sync_fd(destination_parent_descriptor)
        if source_absolute.parent != destination_absolute.parent:
            full_sync_fd(source_parent_descriptor)
    finally:
        os.close(source_descriptor)
        os.close(source_parent_descriptor)
        os.close(destination_parent_descriptor)


def durable_remove_private_file(path: Path) -> None:
    """Unlink one exact private file and durably publish its absence."""

    absolute = _absolute_lexical(path)
    _assert_no_symlink_components(absolute.parent)
    try:
        parent = absolute.parent.lstat()
    except OSError as error:
        raise ReleaseContractError(
            "Durable removal parent is unavailable"
        ) from error
    if (
        not stat.S_ISDIR(parent.st_mode)
        or stat.S_IMODE(parent.st_mode) != 0o700
        or parent.st_uid != os.geteuid()
    ):
        raise ReleaseContractError(
            "Durable removal parent must be owner-controlled mode 0700"
        )
    parent_descriptor = _open_directory_no_follow(absolute.parent)
    if not os.path.lexists(absolute):
        # Retry after a crash between unlink visibility and the original
        # directory barrier. Absence is accepted only after it is re-published.
        try:
            full_sync_fd(parent_descriptor)
        finally:
            os.close(parent_descriptor)
        return
    expected = absolute.lstat()
    if (
        not stat.S_ISREG(expected.st_mode)
        or stat.S_IMODE(expected.st_mode) != 0o600
        or expected.st_uid != os.geteuid()
        or expected.st_nlink != 1
    ):
        os.close(parent_descriptor)
        raise ReleaseContractError(
            "Durable removal target must be a private single-link file"
        )
    flags = os.O_RDONLY | os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    descriptor = os.open(
        absolute.name,
        flags,
        dir_fd=parent_descriptor,
    )
    try:
        opened = os.fstat(descriptor)
        current = os.stat(
            absolute.name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        expected_identity = (expected.st_dev, expected.st_ino)
        if (
            (opened.st_dev, opened.st_ino) != expected_identity
            or (current.st_dev, current.st_ino) != expected_identity
        ):
            raise ReleaseContractError(
                "Durable removal target changed before unlink"
            )
        os.unlink(absolute.name, dir_fd=parent_descriptor)
        if os.path.lexists(absolute):
            raise ReleaseContractError(
                "Durable removal target still exists after unlink"
            )
        full_sync_fd(parent_descriptor)
    finally:
        os.close(descriptor)
        os.close(parent_descriptor)


def durable_rename_private_fence_no_replace(
    source: Path,
    destination: Path,
) -> None:
    """Durably move an exact private ``context``-only fence directory."""

    source_absolute = _absolute_lexical(source)
    destination_absolute = _absolute_lexical(destination)
    _assert_no_symlink_components(source_absolute)
    _assert_no_symlink_components(destination_absolute.parent)
    try:
        source_details = source_absolute.lstat()
        source_parent_details = source_absolute.parent.lstat()
        destination_parent_details = destination_absolute.parent.lstat()
    except OSError as error:
        raise ReleaseContractError("Private fence rename paths are incomplete") from error
    if (
        not stat.S_ISDIR(source_details.st_mode)
        or stat.S_IMODE(source_details.st_mode) != 0o700
        or source_details.st_uid != os.geteuid()
        or not stat.S_ISDIR(source_parent_details.st_mode)
        or not stat.S_ISDIR(destination_parent_details.st_mode)
        or stat.S_IMODE(source_parent_details.st_mode) != 0o700
        or stat.S_IMODE(destination_parent_details.st_mode) != 0o700
        or source_parent_details.st_uid != os.geteuid()
        or destination_parent_details.st_uid != os.geteuid()
        or source_details.st_dev != destination_parent_details.st_dev
        or os.path.lexists(destination_absolute)
    ):
        raise ReleaseContractError(
            "Private fence rename requires an absent same-filesystem destination"
        )
    entries = list(os.scandir(source_absolute))
    if len(entries) != 1 or entries[0].name != "context":
        raise ReleaseContractError(
            "Private fence must contain exactly one context file"
        )
    context = source_absolute / "context"
    context_details = context.lstat()
    if (
        not stat.S_ISREG(context_details.st_mode)
        or stat.S_IMODE(context_details.st_mode) != 0o600
        or context_details.st_uid != os.geteuid()
        or context_details.st_nlink != 1
        or context_details.st_dev != source_details.st_dev
    ):
        raise ReleaseContractError(
            "Private fence context must be owner-controlled mode 0600"
        )

    source_parent_descriptor = _open_directory_no_follow(source_absolute.parent)
    destination_parent_descriptor = _open_directory_no_follow(
        destination_absolute.parent
    )
    source_directory_descriptor = _open_directory_no_follow(source_absolute)
    context_flags = os.O_RDONLY | os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        context_flags |= os.O_CLOEXEC
    context_descriptor = os.open(
        "context",
        context_flags,
        dir_fd=source_directory_descriptor,
    )
    try:
        opened_context = os.fstat(context_descriptor)
        if (opened_context.st_dev, opened_context.st_ino) != (
            context_details.st_dev,
            context_details.st_ino,
        ):
            raise ReleaseContractError(
                "Private fence context changed before publication"
            )
        full_sync_fd(context_descriptor)
        full_sync_fd(source_directory_descriptor)
        full_sync_fd(source_parent_descriptor)
        _publish_file_no_replace(source_absolute, destination_absolute)
        moved = destination_absolute.lstat()
        moved_context = (destination_absolute / "context").lstat()
        if (
            not stat.S_ISDIR(moved.st_mode)
            or (moved.st_dev, moved.st_ino)
            != (source_details.st_dev, source_details.st_ino)
            or (moved_context.st_dev, moved_context.st_ino)
            != (context_details.st_dev, context_details.st_ino)
            or os.path.lexists(source_absolute)
        ):
            raise ReleaseContractError("Private fence rename postconditions failed")
        full_sync_fd(source_directory_descriptor)
        full_sync_fd(destination_parent_descriptor)
        if source_absolute.parent != destination_absolute.parent:
            full_sync_fd(source_parent_descriptor)
    finally:
        os.close(context_descriptor)
        os.close(source_directory_descriptor)
        os.close(source_parent_descriptor)
        os.close(destination_parent_descriptor)


def ensure_private_directory(path: Path) -> None:
    """Create and durably publish an owner-controlled 0700 directory path."""

    _ensure_private_directory(path)


def durability_barrier_private_file(path: Path) -> None:
    """Fsync one private file and its private parent directory."""

    absolute = _absolute_lexical(path)
    _assert_no_symlink_components(absolute)
    try:
        details = absolute.lstat()
        parent_details = absolute.parent.lstat()
    except OSError as error:
        raise ReleaseContractError(
            "Durability barrier private-file path cannot be inspected"
        ) from error
    if (
        not stat.S_ISREG(details.st_mode)
        or stat.S_IMODE(details.st_mode) != 0o600
        or details.st_uid != os.geteuid()
        or details.st_nlink != 1
        or not stat.S_ISDIR(parent_details.st_mode)
        or stat.S_IMODE(parent_details.st_mode) != 0o700
        or parent_details.st_uid != os.geteuid()
        or details.st_dev != parent_details.st_dev
    ):
        raise ReleaseContractError(
            "Durability barrier requires one private single-link file"
        )
    parent_descriptor = _open_directory_no_follow(absolute.parent)
    flags = os.O_RDONLY | os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    descriptor = os.open(absolute.name, flags, dir_fd=parent_descriptor)
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (details.st_dev, details.st_ino):
            raise ReleaseContractError(
                "Durability barrier private file changed during inspection"
            )
        full_sync_fd(descriptor)
        full_sync_fd(parent_descriptor)
    finally:
        os.close(descriptor)
        os.close(parent_descriptor)


def validate_private_tree(path: Path) -> None:
    """Fail closed unless every entry is a private, local, ordinary tree node."""

    absolute = _absolute_lexical(path)
    _assert_no_symlink_components(absolute)
    try:
        root = absolute.lstat()
    except OSError as error:
        raise ReleaseContractError("Private tree root cannot be inspected") from error
    if (
        not stat.S_ISDIR(root.st_mode)
        or stat.S_IMODE(root.st_mode) != 0o700
        or root.st_uid != os.geteuid()
        or getattr(root, "st_flags", 0) != 0
        or _extended_attributes(absolute)
        or _has_extended_acl(absolute)
    ):
        raise ReleaseContractError(
            "Private tree root must be owner-controlled mode 0700"
        )
    root_device = root.st_dev

    def fail_walk(error: OSError) -> None:
        raise ReleaseContractError(
            "Private tree traversal could not inspect every entry"
        ) from error

    for current, directories, files in os.walk(
        absolute,
        topdown=True,
        followlinks=False,
        onerror=fail_walk,
    ):
        directories.sort()
        files.sort()
        current_path = Path(current)
        for name, expected_directory in [
            *((name, True) for name in directories),
            *((name, False) for name in files),
        ]:
            child = current_path / name
            try:
                details = child.lstat()
            except OSError as error:
                raise ReleaseContractError(
                    "Private tree entry cannot be inspected"
                ) from error
            expected_mode = 0o700 if expected_directory else 0o600
            expected_kind = (
                stat.S_ISDIR(details.st_mode)
                if expected_directory
                else stat.S_ISREG(details.st_mode)
            )
            if (
                not expected_kind
                or stat.S_ISLNK(details.st_mode)
                or stat.S_IMODE(details.st_mode) != expected_mode
                or details.st_uid != os.geteuid()
                or details.st_dev != root_device
                or (not expected_directory and details.st_nlink != 1)
                or getattr(details, "st_flags", 0) != 0
                or _extended_attributes(child)
                or _has_extended_acl(child)
            ):
                raise ReleaseContractError(
                    "Private tree contains an unsafe entry"
                )


def durability_barrier_private_tree(path: Path) -> None:
    """Fsync a closed owner-controlled tree and every directory entry it uses."""

    absolute = _absolute_lexical(path)
    _assert_no_symlink_components(absolute)
    root = absolute.lstat()
    if (
        not stat.S_ISDIR(root.st_mode)
        or stat.S_IMODE(root.st_mode) != 0o700
        or root.st_uid != os.geteuid()
    ):
        raise ReleaseContractError(
            "Durability barrier root must be an owner-controlled mode 0700 directory"
        )
    root_device = root.st_dev
    directories: list[Path] = []
    for current, child_directories, files in os.walk(
        absolute,
        topdown=True,
        followlinks=False,
        onerror=lambda error: (_ for _ in ()).throw(
            ReleaseContractError(
                "Durability barrier could not traverse the complete tree"
            )
        ),
    ):
        current_path = Path(current)
        current_details = current_path.lstat()
        if (
            not stat.S_ISDIR(current_details.st_mode)
            or stat.S_IMODE(current_details.st_mode) != 0o700
            or current_details.st_uid != os.geteuid()
            or current_details.st_dev != root_device
        ):
            raise ReleaseContractError(
                "Durability barrier found an unsafe private directory"
            )
        directories.append(current_path)
        for name in child_directories:
            child = current_path / name
            details = child.lstat()
            if stat.S_ISLNK(details.st_mode):
                raise ReleaseContractError(
                    "Durability barrier refuses symbolic links"
                )
        for name in files:
            child = current_path / name
            details = child.lstat()
            if stat.S_ISLNK(details.st_mode):
                raise ReleaseContractError(
                    "Durability barrier refuses symbolic links"
                )
            if (
                not stat.S_ISREG(details.st_mode)
                or details.st_uid != os.geteuid()
                or details.st_dev != root_device
                or details.st_nlink != 1
                or stat.S_IMODE(details.st_mode) & 0o077
            ):
                raise ReleaseContractError(
                    "Durability barrier found an unsafe private file"
                )
            parent_descriptor = _open_directory_no_follow(current_path)
            flags = os.O_RDONLY | os.O_NOFOLLOW
            if hasattr(os, "O_CLOEXEC"):
                flags |= os.O_CLOEXEC
            descriptor = os.open(name, flags, dir_fd=parent_descriptor)
            try:
                opened = os.fstat(descriptor)
                if (opened.st_dev, opened.st_ino) != (
                    details.st_dev,
                    details.st_ino,
                ):
                    raise ReleaseContractError(
                        "Durability barrier file changed while it was opened"
                    )
                full_sync_fd(descriptor)
            finally:
                os.close(descriptor)
                os.close(parent_descriptor)
    for directory in reversed(directories):
        descriptor = _open_directory_no_follow(directory)
        try:
            full_sync_fd(descriptor)
        finally:
            os.close(descriptor)
    parent_descriptor = _open_directory_no_follow(absolute.parent)
    try:
        full_sync_fd(parent_descriptor)
    finally:
        os.close(parent_descriptor)


def write_private_json_no_clobber(path: Path, payload: Mapping[str, Any]) -> None:
    """Durably stage and atomically publish one closed receipt."""

    _assert_no_embedded_secret(payload)
    absolute = _absolute_lexical(path)
    if absolute.name in {"", ".", ".."}:
        raise ReleaseContractError("Release receipt path is invalid")
    serialized = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    parent = _ensure_private_directory(absolute.parent)
    parent_descriptor = _open_directory_no_follow(parent)
    created_identity: tuple[int, int] | None = None
    pending = parent / f".{absolute.name}.pending.{os.getpid()}.{uuid4().hex}"
    try:
        if os.path.lexists(absolute):
            raise ReleaseContractError(
                f"Refusing to replace existing release receipt {absolute}"
            )
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        try:
            descriptor = os.open(pending.name, flags, 0o600, dir_fd=parent_descriptor)
        except OSError as error:
            raise ReleaseContractError(
                "Release receipt could not be created safely"
            ) from error
        opened = os.fstat(descriptor)
        created_identity = (opened.st_dev, opened.st_ino)
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb", closefd=True) as destination:
            destination.write(serialized)
            destination.flush()
            full_sync_fd(destination.fileno())
            written = os.fstat(destination.fileno())
        linked = os.stat(
            pending.name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISREG(linked.st_mode)
            or stat.S_IMODE(linked.st_mode) != 0o600
            or linked.st_uid != os.geteuid()
            or linked.st_nlink != 1
            or (linked.st_dev, linked.st_ino) != created_identity
            or (written.st_dev, written.st_ino) != created_identity
        ):
            raise ReleaseContractError(
                "Release receipt did not remain a private single-link file"
            )
        _publish_file_no_replace(pending, absolute)
        published = os.stat(
            absolute.name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISREG(published.st_mode)
            or stat.S_IMODE(published.st_mode) != 0o600
            or published.st_uid != os.geteuid()
            or published.st_nlink != 1
            or (published.st_dev, published.st_ino) != created_identity
        ):
            raise ReleaseContractError(
                "Published release receipt is not the staged private file"
            )
        full_sync_fd(parent_descriptor)
    finally:
        os.close(parent_descriptor)


def _reject_duplicate_keys(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ReleaseContractError(f"Release JSON repeats key {key!r}")
        result[key] = value
    return result


def read_private_json(path: Path, *, label: str) -> dict[str, Any]:
    absolute = _assert_private_regular_file(path, label=label)
    if absolute.stat().st_size > _MAX_JSON_BYTES:
        raise ReleaseContractError(f"{label} is unexpectedly large")
    try:
        payload = json.loads(
            absolute.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReleaseContractError(f"{label} is not valid JSON") from error
    if not isinstance(payload, dict):
        raise ReleaseContractError(f"{label} must contain one JSON object")
    _assert_no_embedded_secret(payload)
    return payload


def _assert_no_embedded_secret(value: Any) -> None:
    """Reject common credential material; closed schemas reject unknown fields."""

    if isinstance(value, Mapping):
        for item in value.values():
            _assert_no_embedded_secret(item)
    elif isinstance(value, list):
        for item in value:
            _assert_no_embedded_secret(item)
    elif isinstance(value, str) and any(
        pattern.search(value) for pattern in _SUSPICIOUS_SECRET_TEXT
    ):
        raise ReleaseContractError("Release evidence contains credential-like material")


def _require_shape(
    value: Any,
    keys: set[str] | frozenset[str],
    *,
    label: str,
) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ReleaseContractError(f"{label} has an unsupported JSON shape")
    return value


def bind_private_artifact(path: Path, *, label: str) -> ArtifactBinding:
    absolute = _assert_private_regular_file(path, label=label)
    if not _SAFE_ARTIFACT_NAME.fullmatch(absolute.name):
        raise ReleaseContractError(f"{label} has an unsafe artifact basename")
    return {
        "name": absolute.name,
        "sha256": _sha256_file(absolute),
        "sizeBytes": absolute.stat().st_size,
    }


def _validate_artifact_binding(value: Any, *, label: str) -> ArtifactBinding:
    binding = _require_shape(
        value,
        {"name", "sha256", "sizeBytes"},
        label=label,
    )
    if (
        not isinstance(binding["name"], str)
        or not _SAFE_ARTIFACT_NAME.fullmatch(binding["name"])
        or not isinstance(binding["sha256"], str)
        or not _SHA256.fullmatch(binding["sha256"])
        or isinstance(binding["sizeBytes"], bool)
        or not isinstance(binding["sizeBytes"], int)
        or binding["sizeBytes"] < 0
    ):
        raise ReleaseContractError(f"{label} is invalid")
    return binding


def verify_artifact_binding(
    path: Path,
    expected: Mapping[str, Any],
    *,
    label: str,
) -> None:
    expected_binding = _validate_artifact_binding(expected, label=label)
    if bind_private_artifact(path, label=label) != expected_binding:
        raise ReleaseContractError(f"{label} no longer matches its SHA-256 binding")


def validate_artifact_names(names: set[str] | frozenset[str]) -> None:
    unknown = set(names) - CALLER_ARTIFACTS
    if unknown:
        raise ReleaseContractError(
            f"Unknown release artifact kind(s): {', '.join(sorted(unknown))}"
        )
    if not CORE_ARTIFACTS.issubset(names):
        missing = CORE_ARTIFACTS - set(names)
        raise ReleaseContractError(
            f"Missing required release artifact(s): {', '.join(sorted(missing))}"
        )
    for group, label in (
        (FAMILY_VAULT_ARTIFACTS, "family vault"),
        (STAFF_TRANSPORT_VAULT_ARTIFACTS, "staff/transport vault"),
    ):
        present = set(names) & group
        if present and present != group:
            missing = group - present
            raise ReleaseContractError(
                f"The {label} artifact group is partial; missing "
                f"{', '.join(sorted(missing))}"
            )


def bind_artifacts(paths: Mapping[str, Path]) -> dict[str, ArtifactBinding]:
    validate_artifact_names(set(paths))
    return {
        name: bind_private_artifact(paths[name], label=f"artifact {name}")
        for name in sorted(paths)
    }


def _extended_attributes(path: Path) -> list[str]:
    if hasattr(os, "listxattr"):
        values = list(os.listxattr(path, follow_symlinks=False))
        return [value for value in values if value != "com.apple.provenance"]
    try:
        result = subprocess.run(
            ["/usr/bin/xattr", str(path)],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise ReleaseContractError(
            "physical backup extended metadata could not be inspected"
        ) from error
    return [
        line
        for line in result.stdout.splitlines()
        if line and line != "com.apple.provenance"
    ]


def _has_extended_acl(path: Path) -> bool:
    if sys.platform != "darwin":
        return False
    try:
        result = subprocess.run(
            ["/bin/ls", "-lde", str(path)],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise ReleaseContractError(
            "physical backup ACL metadata could not be inspected"
        ) from error
    return len(result.stdout.splitlines()) != 1


def collect_physical_backup_inventory(pgdata: Path) -> dict[str, Any]:
    """Digest every physical-backup byte, including files pg_verifybackup ignores."""

    root = _absolute_lexical(pgdata)
    _assert_no_symlink_components(root)
    root_details = root.lstat()
    if (
        not stat.S_ISDIR(root_details.st_mode)
        or stat.S_IMODE(root_details.st_mode) != 0o700
        or root_details.st_uid != os.geteuid()
        or getattr(root_details, "st_flags", 0) != 0
        or _extended_attributes(root)
        or _has_extended_acl(root)
    ):
        raise ReleaseContractError(
            "physical backup must be an owner-controlled mode 0700 directory"
        )
    entries: list[dict[str, Any]] = []
    def fail_inventory_walk(error: OSError) -> None:
        raise ReleaseContractError(
            "physical backup inventory traversal was incomplete"
        ) from error

    for current, directories, files in os.walk(
        root,
        followlinks=False,
        onerror=fail_inventory_walk,
    ):
        directories.sort()
        files.sort()
        current_path = Path(current)
        for name in [*directories, *files]:
            path = current_path / name
            details = path.lstat()
            relative = path.relative_to(root).as_posix()
            if (
                stat.S_ISLNK(details.st_mode)
                or details.st_uid != os.geteuid()
                or details.st_dev != root_details.st_dev
                or getattr(details, "st_flags", 0) != 0
                or _extended_attributes(path)
                or _has_extended_acl(path)
            ):
                raise ReleaseContractError(
                    "physical backup contains a link, foreign owner, nested mount "
                    "or unbound extended metadata"
                )
            if stat.S_ISDIR(details.st_mode):
                if stat.S_IMODE(details.st_mode) != 0o700:
                    raise ReleaseContractError(
                        "physical backup contains a non-private directory"
                    )
                kind = "directory"
                size = 0
                digest: str | None = None
            elif stat.S_ISREG(details.st_mode):
                if details.st_nlink != 1:
                    raise ReleaseContractError(
                        "physical backup contains a multiply linked file"
                    )
                if stat.S_IMODE(details.st_mode) != 0o600:
                    raise ReleaseContractError(
                        "physical backup contains a non-private file"
                    )
                kind = "file"
                size = details.st_size
                digest = _sha256_file(path)
            else:
                raise ReleaseContractError(
                    "physical backup contains a socket, device, FIFO or special entry"
                )
            entries.append(
                {
                    "path": relative,
                    "type": kind,
                    "mode": f"{stat.S_IMODE(details.st_mode):04o}",
                    "sizeBytes": size,
                    "sha256": digest,
                }
            )
    entries.sort(key=lambda entry: entry["path"])
    return {
        "format": PHYSICAL_BACKUP_INVENTORY_FORMAT,
        "devicePolicy": "single-device-no-mounts",
        "entries": entries,
        "sha256Tree": hashlib.sha256(_canonical_json(entries)).hexdigest(),
    }


def _validate_physical_backup_inventory(value: Any) -> dict[str, Any]:
    inventory = _require_shape(
        value,
        {
            "format",
            "devicePolicy",
            "entries",
            "sha256Tree",
        },
        label="physical backup inventory",
    )
    if (
        inventory["format"] != PHYSICAL_BACKUP_INVENTORY_FORMAT
        or inventory["devicePolicy"] != "single-device-no-mounts"
        or not isinstance(inventory["entries"], list)
        or not isinstance(inventory["sha256Tree"], str)
        or not _SHA256.fullmatch(inventory["sha256Tree"])
        or hashlib.sha256(_canonical_json(inventory["entries"])).hexdigest()
        != inventory["sha256Tree"]
    ):
        raise ReleaseContractError("physical backup inventory is invalid")
    paths: list[str] = []
    for raw in inventory["entries"]:
        entry = _require_shape(
            raw,
            {"path", "type", "mode", "sizeBytes", "sha256"},
            label="physical backup inventory entry",
        )
        if (
            not isinstance(entry["path"], str)
            or not entry["path"]
            or entry["path"].startswith("/")
            or ".." in Path(entry["path"]).parts
            or entry["type"] not in {"directory", "file"}
            or not isinstance(entry["mode"], str)
            or not re.fullmatch(r"0[0-7]{3}", entry["mode"])
            or isinstance(entry["sizeBytes"], bool)
            or not isinstance(entry["sizeBytes"], int)
            or entry["sizeBytes"] < 0
        ):
            raise ReleaseContractError("physical backup inventory entry is invalid")
        if entry["type"] == "directory":
            if entry["sizeBytes"] != 0 or entry["sha256"] is not None:
                raise ReleaseContractError(
                    "physical backup directory inventory is invalid"
                )
        elif (
            not isinstance(entry["sha256"], str)
            or not _SHA256.fullmatch(entry["sha256"])
        ):
            raise ReleaseContractError("physical backup file digest is invalid")
        paths.append(entry["path"])
    if paths != sorted(set(paths)):
        raise ReleaseContractError(
            "physical backup inventory paths are duplicated or unsorted"
        )
    return inventory


def create_physical_backup_inventory(
    *,
    pgdata: Path,
    output_path: Path,
) -> dict[str, Any]:
    inventory = collect_physical_backup_inventory(pgdata)
    _validate_physical_backup_inventory(inventory)
    write_private_json_no_clobber(output_path, inventory)
    return inventory


def verify_physical_backup_inventory(
    *,
    pgdata: Path,
    inventory_path: Path,
) -> dict[str, Any]:
    expected = _validate_physical_backup_inventory(
        read_private_json(inventory_path, label="physical backup inventory")
    )
    if collect_physical_backup_inventory(pgdata) != expected:
        raise ReleaseContractError(
            "physical backup tree differs from its complete inventory"
        )
    return expected


def _validate_artifact_bindings(
    value: Any,
    *,
    include_generated: bool,
) -> dict[str, ArtifactBinding]:
    if not isinstance(value, dict):
        raise ReleaseContractError("artifact bindings must be a JSON object")
    allowed = CALLER_ARTIFACTS | (GENERATED_ARTIFACTS if include_generated else set())
    if set(value) - allowed:
        raise ReleaseContractError("artifact bindings contain an unknown kind")
    caller_names = set(value) & CALLER_ARTIFACTS
    validate_artifact_names(caller_names)
    if include_generated and not GENERATED_ARTIFACTS.issubset(value):
        raise ReleaseContractError("generated artifact bindings are incomplete")
    for name, binding in value.items():
        _validate_artifact_binding(binding, label=f"artifact binding {name}")
    return value


def _validate_payload_artifact_bindings(value: Any) -> dict[str, ArtifactBinding]:
    """Validate caller artifacts plus the one non-circular clone binding."""

    if not isinstance(value, dict):
        raise ReleaseContractError("release-payload artifacts must be a JSON object")
    if "release_payload" in value or "clone_certificate" not in value:
        raise ReleaseContractError(
            "release-payload generated artifact bindings are invalid"
        )
    caller_names = set(value) - {"clone_certificate"}
    validate_artifact_names(caller_names)
    for name, binding in value.items():
        _validate_artifact_binding(binding, label=f"artifact binding {name}")
    return value


def _encode_database_value(value: Any) -> Any:
    """Use the backup codec so release and backup row evidence are identical."""

    from scripts.backup_database import encode_value

    return encode_value(value)


def collect_business_evidence(connection: Any) -> dict[str, Any]:
    """Hash every public business row deterministically, excluding Alembic."""

    from sqlalchemy import MetaData, func, select

    metadata = MetaData()
    metadata.reflect(bind=connection, schema="public")
    tables = sorted(
        (
            table
            for table in metadata.tables.values()
            if table.name != "alembic_version"
        ),
        key=lambda table: table.name,
    )
    records: list[dict[str, Any]] = []
    global_digest = hashlib.sha256()
    for table in tables:
        primary_key = list(table.primary_key.columns)
        if not primary_key:
            raise ReleaseContractError(
                f"Business table {table.name!r} has no primary key"
            )
        direct_count = int(
            connection.execute(select(func.count()).select_from(table)).scalar_one()
        )
        table_digest = hashlib.sha256()
        counted = 0
        statement = select(table).order_by(*primary_key)
        for row in connection.execute(statement).mappings():
            line = (
                _canonical_json(
                    {
                        "table": table.name,
                        "row": {
                            key: _encode_database_value(value)
                            for key, value in row.items()
                        },
                    }
                )
                + b"\n"
            )
            table_digest.update(line)
            global_digest.update(line)
            counted += 1
        if counted != direct_count:
            raise ReleaseContractError(
                f"Snapshot count changed while reading business table {table.name!r}"
            )
        records.append(
            {
                "name": table.name,
                "rowCount": counted,
                "sha256Rows": table_digest.hexdigest(),
            }
        )
    return {
        "tables": records,
        "totalRows": sum(record["rowCount"] for record in records),
        "sha256Rows": global_digest.hexdigest(),
    }


def _validate_business_evidence(value: Any) -> dict[str, Any]:
    evidence = _require_shape(
        value,
        {"tables", "totalRows", "sha256Rows"},
        label="business evidence",
    )
    if (
        not isinstance(evidence["tables"], list)
        or isinstance(evidence["totalRows"], bool)
        or not isinstance(evidence["totalRows"], int)
        or evidence["totalRows"] < 0
        or not isinstance(evidence["sha256Rows"], str)
        or not _SHA256.fullmatch(evidence["sha256Rows"])
    ):
        raise ReleaseContractError("business evidence is invalid")
    names: list[str] = []
    total = 0
    for raw in evidence["tables"]:
        table = _require_shape(
            raw,
            {"name", "rowCount", "sha256Rows"},
            label="business table evidence",
        )
        if (
            not isinstance(table["name"], str)
            or not table["name"]
            or table["name"] == "alembic_version"
            or isinstance(table["rowCount"], bool)
            or not isinstance(table["rowCount"], int)
            or table["rowCount"] < 0
            or not isinstance(table["sha256Rows"], str)
            or not _SHA256.fullmatch(table["sha256Rows"])
        ):
            raise ReleaseContractError("business table evidence is invalid")
        names.append(table["name"])
        total += table["rowCount"]
    if names != sorted(set(names)) or total != evidence["totalRows"]:
        raise ReleaseContractError(
            "business evidence inventory or total row count is inconsistent"
        )
    return evidence


_IDENTITY_KEYS = {
    "databaseName",
    "roleName",
    "sessionUser",
    "serverAddress",
    "serverPort",
    "serverVersion",
    "serverVersionNum",
    "dataDirectory",
    "systemIdentifier",
}


def _collect_postgres_identity(connection: Any) -> dict[str, Any]:
    from sqlalchemy import text

    row = (
        connection.execute(
            text(
                "SELECT current_database() AS database_name, "
                "current_user AS role_name, session_user AS session_user, "
                "COALESCE(host(inet_server_addr()),'local') AS server_address, "
                "inet_server_port() AS server_port, "
                "current_setting('server_version') AS server_version, "
                "current_setting('server_version_num')::integer AS server_version_num, "
                "current_setting('data_directory') AS data_directory, "
                "(SELECT system_identifier::text "
                "FROM pg_catalog.pg_control_system()) AS system_identifier"
            )
        )
        .mappings()
        .one()
    )
    return {
        "databaseName": row["database_name"],
        "roleName": row["role_name"],
        "sessionUser": row["session_user"],
        "serverAddress": row["server_address"],
        "serverPort": row["server_port"],
        "serverVersion": row["server_version"],
        "serverVersionNum": row["server_version_num"],
        "dataDirectory": row["data_directory"],
        "systemIdentifier": row["system_identifier"],
    }


def _billing_policy_profile(connection: Any) -> str:
    """Run the frozen 0042 classifier without duplicating its policy catalog."""

    migration = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "0042_billing_policy_recertification.py"
    )
    if not migration.is_file():
        raise ReleaseContractError(
            "The frozen 0042 billing-policy classifier is unavailable"
        )
    specification = importlib.util.spec_from_file_location(
        "_caresync_release_0042_policy",
        migration,
    )
    if specification is None or specification.loader is None:
        raise ReleaseContractError(
            "The frozen 0042 billing-policy classifier cannot be loaded"
        )
    module = importlib.util.module_from_spec(specification)
    try:
        specification.loader.exec_module(module)
        profile = module._classify_policy_rows(  # noqa: SLF001
            module._catalog_policy_rows(connection)  # noqa: SLF001
        )
    except Exception as error:
        raise ReleaseContractError(
            "The 0042 billing-policy catalog failed frozen classification"
        ) from error
    if profile != "A":
        raise ReleaseContractError(
            "Release certification requires exact billing-policy profile A"
        )
    return profile


def _validate_identity(value: Any) -> dict[str, Any]:
    identity = _require_shape(value, _IDENTITY_KEYS, label="PostgreSQL identity")
    string_keys = _IDENTITY_KEYS - {"serverPort", "serverVersionNum"}
    if any(
        not isinstance(identity[key], str) or not identity[key] for key in string_keys
    ):
        raise ReleaseContractError("PostgreSQL identity contains a blank field")
    if (
        isinstance(identity["serverPort"], bool)
        or not isinstance(identity["serverPort"], int)
        or not 1 <= identity["serverPort"] <= 65535
        or isinstance(identity["serverVersionNum"], bool)
        or not isinstance(identity["serverVersionNum"], int)
        or identity["serverVersionNum"] // 10000 != 17
    ):
        raise ReleaseContractError("PostgreSQL identity is not PostgreSQL 17 or later")
    return identity


def collect_snapshot(
    connection: Any,
    *,
    expected_revision: str,
    runtime_certificate_hook: RuntimeCertificateHook | None = None,
    runtime_hook_target: Any | None = None,
) -> Snapshot:
    """Collect one same-transaction PostgreSQL identity and business snapshot."""

    from sqlalchemy import text

    if connection.dialect.name != "postgresql":
        raise ReleaseContractError("Release certification requires PostgreSQL")
    connection.exec_driver_sql("SET TRANSACTION READ ONLY, DEFERRABLE")
    connection.exec_driver_sql("SET LOCAL row_security = off")
    connection.exec_driver_sql("SET LOCAL TIME ZONE 'UTC'")
    role = (
        connection.execute(
            text(
                "SELECT rolsuper, rolbypassrls FROM pg_catalog.pg_roles "
                "WHERE rolname=current_user"
            )
        )
        .mappings()
        .one_or_none()
    )
    if role is None or not (bool(role["rolsuper"]) or bool(role["rolbypassrls"])):
        raise ReleaseContractError(
            "Release evidence role cannot bypass FORCE RLS; refusing partial evidence"
        )
    revisions = list(
        connection.execute(
            text("SELECT version_num FROM public.alembic_version ORDER BY version_num")
        ).scalars()
    )
    if revisions != [expected_revision]:
        raise ReleaseContractError(
            f"Expected exact Alembic revision {expected_revision!r}"
        )
    evidence = collect_business_evidence(connection)
    counts = {
        table["name"]: table["rowCount"]
        for table in evidence["tables"]
        if table["name"] in NEW_0041_TABLES
    }
    if expected_revision == SOURCE_REVISION:
        if counts:
            raise ReleaseContractError("0039 source unexpectedly contains 0041 tables")
        new_counts: dict[str, int | None] = {name: None for name in NEW_0041_TABLES}
        billing_policy_profile: str | None = None
    elif expected_revision == TARGET_REVISION:
        if counts != {name: 0 for name in NEW_0041_TABLES}:
            raise ReleaseContractError(
                "The four 0041 release tables must all exist and be empty"
            )
        new_counts = {name: 0 for name in NEW_0041_TABLES}
        billing_policy_profile = _billing_policy_profile(connection)
    else:
        raise ReleaseContractError("Unsupported release revision")

    if runtime_certificate_hook is None:
        runtime_certificate = {
            "hook": "Database.assert_basic_runtime_identity",
            "status": "not_required",
        }
    else:
        runtime_certificate_hook(runtime_hook_target)
        runtime_certificate = {
            "hook": "Database.assert_basic_runtime_identity",
            "status": "passed",
        }
    return {
        "revision": expected_revision,
        "identity": _collect_postgres_identity(connection),
        "business": evidence,
        "new0041TableCounts": new_counts,
        "billingPolicyProfile": billing_policy_profile,
        "runtimeCertificate": runtime_certificate,
    }


def _validate_snapshot(
    value: Any,
    *,
    expected_revision: str,
    runtime_required: bool,
) -> Snapshot:
    snapshot = _require_shape(
        value,
        {
            "revision",
            "identity",
            "business",
            "new0041TableCounts",
            "billingPolicyProfile",
            "runtimeCertificate",
        },
        label="database snapshot",
    )
    if snapshot["revision"] != expected_revision:
        raise ReleaseContractError("database snapshot has the wrong revision")
    _validate_identity(snapshot["identity"])
    _validate_business_evidence(snapshot["business"])
    counts = snapshot["new0041TableCounts"]
    if not isinstance(counts, dict) or set(counts) != set(NEW_0041_TABLES):
        raise ReleaseContractError("0041 table count evidence has the wrong shape")
    expected_count = 0 if expected_revision == TARGET_REVISION else None
    if any(value != expected_count for value in counts.values()):
        raise ReleaseContractError("0041 table count evidence is inconsistent")
    expected_profile = "A" if expected_revision == TARGET_REVISION else None
    if snapshot["billingPolicyProfile"] != expected_profile:
        raise ReleaseContractError(
            "database snapshot has the wrong billing-policy profile"
        )
    certificate = _require_shape(
        snapshot["runtimeCertificate"],
        {"hook", "status"},
        label="runtime certificate",
    )
    expected_status = "passed" if runtime_required else "not_required"
    if (
        certificate["hook"] != "Database.assert_basic_runtime_identity"
        or certificate["status"] != expected_status
    ):
        raise ReleaseContractError("runtime certificate did not pass the required hook")
    return snapshot


_RETAINED_IDENTITY_KEYS = {
    "databaseName",
    "dataDirectory",
    "serverPort",
    "systemIdentifier",
}


def _read_retained_identity(path: Path) -> dict[str, Any]:
    """Read the launcher's pinned retained-cluster identity without ambiguity."""

    absolute = _assert_private_regular_file(path, label="retained identity file")
    if absolute.stat().st_size > 16 * 1024:
        raise ReleaseContractError("retained identity file is unexpectedly large")
    try:
        lines = absolute.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as error:
        raise ReleaseContractError("retained identity file is unreadable") from error
    values: dict[str, str] = {}
    for line in lines:
        if "=" not in line:
            raise ReleaseContractError("retained identity file has an invalid line")
        key, value = line.split("=", 1)
        if key in values or not key or not value:
            raise ReleaseContractError("retained identity file is ambiguous")
        values[key] = value
    expected = {"data_directory", "system_identifier", "port", "database"}
    if set(values) != expected:
        raise ReleaseContractError("retained identity file has the wrong shape")
    try:
        server_port = int(values["port"])
    except ValueError as error:
        raise ReleaseContractError("retained identity port is invalid") from error
    identity = {
        "databaseName": values["database"],
        "dataDirectory": values["data_directory"],
        "serverPort": server_port,
        "systemIdentifier": values["system_identifier"],
    }
    return _validate_retained_identity(identity)


def _validate_retained_identity(value: Any) -> dict[str, Any]:
    identity = _require_shape(
        value,
        _RETAINED_IDENTITY_KEYS,
        label="retained PostgreSQL identity",
    )
    if (
        identity["databaseName"] != "caresync"
        or identity["serverPort"] != 5434
        or not isinstance(identity["dataDirectory"], str)
        or not identity["dataDirectory"].startswith("/")
        or not isinstance(identity["systemIdentifier"], str)
        or not identity["systemIdentifier"].isdigit()
    ):
        raise ReleaseContractError("retained PostgreSQL identity is invalid")
    return identity


_PHYSICAL_OBSERVATION_KEYS = {
    "format",
    "phase",
    "rehearsalId",
    "observedAt",
    "sourceRevision",
    "retainedIdentityFile",
    "physicalBackupManifest",
    "physicalBackupInventory",
    "retainedIdentity",
    "rehearsedSource",
    "onlineAttestation",
}


_PHYSICAL_ONLINE_ATTESTATION_KEYS = {
    "endpoint",
    "isInRecovery",
    "writerRoleStates",
    "otherClientSessions",
}


def _validate_physical_online_attestation(
    value: Any,
    *,
    rehearsed_source: Snapshot,
) -> dict[str, Any]:
    attestation = _require_shape(
        value,
        _PHYSICAL_ONLINE_ATTESTATION_KEYS,
        label="physical rehearsal online attestation",
    )
    roles = _require_shape(
        attestation["writerRoleStates"],
        {
            "caresync_basic_app",
            "caresync_transport_evidence_ingest",
        },
        label="physical rehearsal writer-role states",
    )
    identity = _validate_identity(rehearsed_source["identity"])
    if (
        attestation["endpoint"]
        != f"127.0.0.1:{identity['serverPort']}"
        or identity["serverAddress"] != "127.0.0.1"
        or attestation["isInRecovery"] is not False
        or roles["caresync_basic_app"] != "nologin"
        or roles["caresync_transport_evidence_ingest"] != "nologin"
        or isinstance(attestation["otherClientSessions"], bool)
        or not isinstance(attestation["otherClientSessions"], int)
        or attestation["otherClientSessions"] != 0
    ):
        raise ReleaseContractError(
            "physical rehearsal online isolation attestation is invalid"
        )
    return attestation


def _validate_physical_rehearsal_observation(payload: Any) -> dict[str, Any]:
    observation = _require_shape(
        payload,
        _PHYSICAL_OBSERVATION_KEYS,
        label="physical backup rehearsal observation",
    )
    if (
        observation["format"] != PHYSICAL_REHEARSAL_OBSERVATION_FORMAT
        or observation["phase"] != "physical_backup_online_observation"
        or not isinstance(observation["rehearsalId"], str)
        or not observation["rehearsalId"]
        or not isinstance(observation["observedAt"], str)
        or not observation["observedAt"]
        or observation["sourceRevision"] != SOURCE_REVISION
    ):
        raise ReleaseContractError(
            "physical backup rehearsal observation metadata is invalid"
        )
    _validate_artifact_binding(
        observation["retainedIdentityFile"],
        label="retained identity file binding",
    )
    _validate_artifact_binding(
        observation["physicalBackupManifest"],
        label="physical backup manifest binding",
    )
    _validate_artifact_binding(
        observation["physicalBackupInventory"],
        label="physical backup inventory binding",
    )
    retained = _validate_retained_identity(observation["retainedIdentity"])
    rehearsed = _validate_snapshot(
        observation["rehearsedSource"],
        expected_revision=SOURCE_REVISION,
        runtime_required=False,
    )
    _validate_physical_online_attestation(
        observation["onlineAttestation"],
        rehearsed_source=rehearsed,
    )
    rehearsal_identity = _validate_identity(rehearsed["identity"])
    if (
        rehearsal_identity["databaseName"] != retained["databaseName"]
        or rehearsal_identity["systemIdentifier"] != retained["systemIdentifier"]
        or rehearsal_identity["serverPort"] < 55000
        or rehearsal_identity["serverPort"] > 60999
        or rehearsal_identity["serverPort"] in {5432, 5433, 5434}
        or rehearsal_identity["dataDirectory"] == retained["dataDirectory"]
    ):
        raise ReleaseContractError(
            "physical backup did not boot as a distinct retained-source rehearsal"
        )
    return observation


def create_physical_rehearsal_observation(
    *,
    rehearsal_snapshot: Snapshot,
    physical_backup_manifest_path: Path,
    physical_backup_inventory_path: Path,
    retained_identity_path: Path,
    observation_path: Path,
    online_attestation: Mapping[str, Any],
) -> dict[str, Any]:
    """Capture the online exact-0039 state of a high-port physical copy."""

    retained = _read_retained_identity(retained_identity_path)
    _validate_physical_backup_inventory(
        read_private_json(
            physical_backup_inventory_path,
            label="physical backup inventory",
        )
    )
    _validate_snapshot(
        rehearsal_snapshot,
        expected_revision=SOURCE_REVISION,
        runtime_required=False,
    )
    observation = {
        "format": PHYSICAL_REHEARSAL_OBSERVATION_FORMAT,
        "phase": "physical_backup_online_observation",
        "rehearsalId": str(uuid4()),
        "observedAt": _utc_now(),
        "sourceRevision": SOURCE_REVISION,
        "retainedIdentityFile": bind_private_artifact(
            retained_identity_path,
            label="retained identity file",
        ),
        "physicalBackupManifest": bind_private_artifact(
            physical_backup_manifest_path,
            label="physical backup manifest",
        ),
        "physicalBackupInventory": bind_private_artifact(
            physical_backup_inventory_path,
            label="physical backup inventory",
        ),
        "retainedIdentity": retained,
        "rehearsedSource": rehearsal_snapshot,
        "onlineAttestation": dict(online_attestation),
    }
    _validate_physical_rehearsal_observation(observation)
    write_private_json_no_clobber(observation_path, observation)
    return observation


_PHYSICAL_REHEARSAL_KEYS = {
    "format",
    "phase",
    "rehearsalId",
    "createdAt",
    "sourceRevision",
    "observation",
    "retainedIdentityFile",
    "physicalBackupManifest",
    "physicalBackupInventory",
    "retainedIdentity",
    "rehearsedSource",
    "onlineAttestation",
    "offlineControl",
}


def _validate_physical_rehearsal_receipt(payload: Any) -> dict[str, Any]:
    receipt = _require_shape(
        payload,
        _PHYSICAL_REHEARSAL_KEYS,
        label="physical backup rehearsal receipt",
    )
    if (
        receipt["format"] != PHYSICAL_REHEARSAL_RECEIPT_FORMAT
        or receipt["phase"] != "physical_backup_rehearsed_and_stopped"
        or not isinstance(receipt["rehearsalId"], str)
        or not receipt["rehearsalId"]
        or not isinstance(receipt["createdAt"], str)
        or not receipt["createdAt"]
        or receipt["sourceRevision"] != SOURCE_REVISION
    ):
        raise ReleaseContractError(
            "physical backup rehearsal receipt metadata is invalid"
        )
    _validate_artifact_binding(
        receipt["observation"],
        label="physical backup rehearsal observation binding",
    )
    _validate_artifact_binding(
        receipt["retainedIdentityFile"],
        label="retained identity file binding",
    )
    _validate_artifact_binding(
        receipt["physicalBackupManifest"],
        label="physical backup manifest binding",
    )
    _validate_artifact_binding(
        receipt["physicalBackupInventory"],
        label="physical backup inventory binding",
    )
    retained = _validate_retained_identity(receipt["retainedIdentity"])
    rehearsed = _validate_snapshot(
        receipt["rehearsedSource"],
        expected_revision=SOURCE_REVISION,
        runtime_required=False,
    )
    _validate_physical_online_attestation(
        receipt["onlineAttestation"],
        rehearsed_source=rehearsed,
    )
    rehearsal_identity = _validate_identity(rehearsed["identity"])
    offline = _require_shape(
        receipt["offlineControl"],
        {"clusterState", "systemIdentifier", "dataDirectory"},
        label="offline rehearsal control evidence",
    )
    if (
        offline["clusterState"] != "shut down"
        or offline["systemIdentifier"] != retained["systemIdentifier"]
        or offline["dataDirectory"] != rehearsal_identity["dataDirectory"]
        or rehearsal_identity["databaseName"] != retained["databaseName"]
        or rehearsal_identity["systemIdentifier"] != retained["systemIdentifier"]
        or rehearsal_identity["serverPort"] < 55000
        or rehearsal_identity["serverPort"] > 60999
        or rehearsal_identity["serverPort"] in {5432, 5433, 5434}
        or rehearsal_identity["dataDirectory"] == retained["dataDirectory"]
    ):
        raise ReleaseContractError(
            "physical backup rehearsal lacks a clean stopped retained-source proof"
        )
    return receipt


def create_physical_rehearsal_receipt(
    *,
    observation_path: Path,
    physical_backup_manifest_path: Path,
    physical_backup_inventory_path: Path,
    retained_identity_path: Path,
    offline_control: Mapping[str, Any],
    receipt_path: Path,
) -> dict[str, Any]:
    """Seal online evidence only after the rehearsal copy is cleanly stopped."""

    observation = _validate_physical_rehearsal_observation(
        read_private_json(
            observation_path,
            label="physical backup rehearsal observation",
        )
    )
    retained = _read_retained_identity(retained_identity_path)
    verify_artifact_binding(
        physical_backup_manifest_path,
        observation["physicalBackupManifest"],
        label="physical backup manifest",
    )
    verify_artifact_binding(
        retained_identity_path,
        observation["retainedIdentityFile"],
        label="retained identity file",
    )
    verify_artifact_binding(
        physical_backup_inventory_path,
        observation["physicalBackupInventory"],
        label="physical backup inventory",
    )
    if observation["retainedIdentity"] != retained:
        raise ReleaseContractError(
            "physical rehearsal observation retained identity changed"
        )
    receipt = {
        "format": PHYSICAL_REHEARSAL_RECEIPT_FORMAT,
        "phase": "physical_backup_rehearsed_and_stopped",
        "rehearsalId": observation["rehearsalId"],
        "createdAt": _utc_now(),
        "sourceRevision": SOURCE_REVISION,
        "observation": bind_private_artifact(
            observation_path,
            label="physical backup rehearsal observation",
        ),
        "retainedIdentityFile": observation["retainedIdentityFile"],
        "physicalBackupManifest": observation["physicalBackupManifest"],
        "physicalBackupInventory": observation["physicalBackupInventory"],
        "retainedIdentity": retained,
        "rehearsedSource": observation["rehearsedSource"],
        "onlineAttestation": observation["onlineAttestation"],
        "offlineControl": dict(offline_control),
    }
    _validate_physical_rehearsal_receipt(receipt)
    write_private_json_no_clobber(receipt_path, receipt)
    return receipt


def collect_offline_rehearsal_control(pgdata: Path) -> dict[str, str]:
    """Read pg_controldata only after a private rehearsal cluster is stopped."""

    absolute = _absolute_lexical(pgdata)
    _assert_no_symlink_components(absolute)
    try:
        details = absolute.lstat()
        version = (absolute / "PG_VERSION").read_text(encoding="ascii").strip()
    except (OSError, UnicodeDecodeError) as error:
        raise ReleaseContractError(
            "offline rehearsal PGDATA is incomplete"
        ) from error
    if (
        not stat.S_ISDIR(details.st_mode)
        or stat.S_IMODE(details.st_mode) != 0o700
        or details.st_uid != os.geteuid()
        or (absolute / "postmaster.pid").exists()
        or version != "17"
    ):
        raise ReleaseContractError(
            "offline rehearsal PGDATA is not private, stopped PostgreSQL 17"
        )
    pg_bin = Path(
        os.getenv("CARESYNC_PG_BIN", "/opt/homebrew/opt/postgresql@17/bin")
    )
    try:
        result = subprocess.run(
            [str(pg_bin / "pg_controldata"), str(absolute)],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
            env={**os.environ, "LC_ALL": "C"},
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise ReleaseContractError(
            "offline rehearsal pg_controldata inspection failed"
        ) from error
    values: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            values[key.strip()] = value.strip()
    system_identifier = values.get("Database system identifier", "")
    cluster_state = values.get("Database cluster state", "")
    if not system_identifier.isdigit() or cluster_state != "shut down":
        raise ReleaseContractError(
            "physical rehearsal did not reach a clean shutdown state"
        )
    return {
        "clusterState": cluster_state,
        "systemIdentifier": system_identifier,
        "dataDirectory": str(absolute.resolve(strict=True)),
    }


def verify_physical_rehearsal_receipt(
    *,
    rehearsal_receipt_path: Path,
    rehearsal_observation_path: Path,
    physical_backup_manifest_path: Path,
    physical_backup_inventory_path: Path,
    retained_identity_path: Path,
    expected_source_snapshot: Snapshot | None = None,
) -> dict[str, Any]:
    """Reopen rehearsal evidence and optionally compare it with retained 0039."""

    receipt = _validate_physical_rehearsal_receipt(
        read_private_json(
            rehearsal_receipt_path,
            label="physical backup rehearsal receipt",
        )
    )
    observation = _validate_physical_rehearsal_observation(
        read_private_json(
            rehearsal_observation_path,
            label="physical backup rehearsal observation",
        )
    )
    verify_artifact_binding(
        rehearsal_observation_path,
        receipt["observation"],
        label="physical backup rehearsal observation",
    )
    if (
        receipt["rehearsalId"] != observation["rehearsalId"]
        or receipt["retainedIdentityFile"] != observation["retainedIdentityFile"]
        or receipt["physicalBackupManifest"]
        != observation["physicalBackupManifest"]
        or receipt["physicalBackupInventory"]
        != observation["physicalBackupInventory"]
        or receipt["retainedIdentity"] != observation["retainedIdentity"]
        or receipt["rehearsedSource"] != observation["rehearsedSource"]
        or receipt["onlineAttestation"] != observation["onlineAttestation"]
    ):
        raise ReleaseContractError(
            "physical rehearsal receipt differs from its online observation"
        )
    verify_artifact_binding(
        physical_backup_manifest_path,
        receipt["physicalBackupManifest"],
        label="physical backup manifest",
    )
    verify_artifact_binding(
        physical_backup_inventory_path,
        receipt["physicalBackupInventory"],
        label="physical backup inventory",
    )
    _validate_physical_backup_inventory(
        read_private_json(
            physical_backup_inventory_path,
            label="physical backup inventory",
        )
    )
    verify_artifact_binding(
        retained_identity_path,
        receipt["retainedIdentityFile"],
        label="retained identity file",
    )
    retained = _read_retained_identity(retained_identity_path)
    if retained != receipt["retainedIdentity"]:
        raise ReleaseContractError(
            "retained identity file differs from physical rehearsal evidence"
        )
    if expected_source_snapshot is not None:
        source = _validate_snapshot(
            expected_source_snapshot,
            expected_revision=SOURCE_REVISION,
            runtime_required=False,
        )
        rehearsed = receipt["rehearsedSource"]
        source_identity = _validate_identity(source["identity"])
        rehearsal_identity = _validate_identity(rehearsed["identity"])
        if (
            source["business"] != rehearsed["business"]
            or source["new0041TableCounts"] != rehearsed["new0041TableCounts"]
            or source["billingPolicyProfile"] != rehearsed["billingPolicyProfile"]
            or source["runtimeCertificate"] != rehearsed["runtimeCertificate"]
            or source_identity["databaseName"] != retained["databaseName"]
            or source_identity["dataDirectory"] != retained["dataDirectory"]
            or source_identity["serverPort"] != retained["serverPort"]
            or source_identity["systemIdentifier"] != retained["systemIdentifier"]
            or source_identity["roleName"] != rehearsal_identity["roleName"]
        ):
            raise ReleaseContractError(
                "physical rehearsal is not the retained source captured by "
                "the candidate"
            )
    return receipt


_RUNTIME_STATE_KEYS = {
    "revision",
    "identity",
    "billingPolicyProfile",
    "runtimeCertificate",
}


def collect_runtime_state(
    connection: Any,
    *,
    runtime_certificate_hook: RuntimeCertificateHook,
    runtime_hook_target: Any | None = None,
) -> dict[str, Any]:
    """Certify live identity/schema/runtime without constraining later app writes."""

    from sqlalchemy import text

    if connection.dialect.name != "postgresql":
        raise ReleaseContractError("Release finalization requires PostgreSQL")
    connection.exec_driver_sql("SET TRANSACTION READ ONLY, DEFERRABLE")
    connection.exec_driver_sql("SET LOCAL TIME ZONE 'UTC'")
    revisions = list(
        connection.execute(
            text("SELECT version_num FROM public.alembic_version ORDER BY version_num")
        ).scalars()
    )
    if revisions != [TARGET_REVISION]:
        raise ReleaseContractError(
            f"Expected exact Alembic revision {TARGET_REVISION!r}"
        )
    profile = _billing_policy_profile(connection)
    runtime_certificate_hook(runtime_hook_target)
    return {
        "revision": TARGET_REVISION,
        "identity": _collect_postgres_identity(connection),
        "billingPolicyProfile": profile,
        "runtimeCertificate": {
            "hook": "Database.assert_basic_runtime_identity",
            "status": "passed",
        },
    }


def _validate_runtime_state(value: Any) -> dict[str, Any]:
    state = _require_shape(
        value,
        _RUNTIME_STATE_KEYS,
        label="live runtime state",
    )
    if state["revision"] != TARGET_REVISION or state["billingPolicyProfile"] != "A":
        raise ReleaseContractError(
            "live runtime state is not exact 0043 with frozen billing profile A"
        )
    _validate_identity(state["identity"])
    certificate = _require_shape(
        state["runtimeCertificate"],
        {"hook", "status"},
        label="live runtime certificate",
    )
    if (
        certificate["hook"] != "Database.assert_basic_runtime_identity"
        or certificate["status"] != "passed"
    ):
        raise ReleaseContractError("live runtime certificate did not pass")
    return state


def _business_table_map(snapshot: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    evidence = _validate_business_evidence(snapshot["business"])
    return {table["name"]: table for table in evidence["tables"]}


def verify_source_candidate(source: Snapshot, candidate: Snapshot) -> None:
    _validate_snapshot(
        source, expected_revision=SOURCE_REVISION, runtime_required=False
    )
    _validate_snapshot(
        candidate, expected_revision=TARGET_REVISION, runtime_required=True
    )
    source_tables = _business_table_map(source)
    candidate_tables = _business_table_map(candidate)
    expected_candidate_names = set(source_tables) | set(NEW_0041_TABLES)
    if set(candidate_tables) != expected_candidate_names:
        raise ReleaseContractError(
            "Candidate business-table inventory is not source plus the four 0041 tables"
        )
    for name, source_evidence in source_tables.items():
        if candidate_tables[name] != source_evidence:
            raise ReleaseContractError(
                f"Candidate changed pre-existing business table {name!r}"
            )
    empty_digest = hashlib.sha256().hexdigest()
    for name in NEW_0041_TABLES:
        if candidate_tables[name] != {
            "name": name,
            "rowCount": 0,
            "sha256Rows": empty_digest,
        }:
            raise ReleaseContractError(f"Candidate 0041 table {name!r} is not empty")
    source_identity = _validate_identity(source["identity"])
    candidate_identity = _validate_identity(candidate["identity"])
    if source_identity["databaseName"] != candidate_identity["databaseName"]:
        raise ReleaseContractError("Candidate database name differs from source")
    if source_identity["roleName"] != candidate_identity["roleName"]:
        raise ReleaseContractError("Candidate evidence role differs from source")
    if (
        source_identity["systemIdentifier"] == candidate_identity["systemIdentifier"]
        or source_identity["dataDirectory"] == candidate_identity["dataDirectory"]
    ):
        raise ReleaseContractError(
            "Candidate is not a distinct disposable PostgreSQL cluster"
        )


def verify_candidate_promoted(candidate: Snapshot, promoted: Snapshot) -> None:
    _validate_snapshot(
        candidate, expected_revision=TARGET_REVISION, runtime_required=True
    )
    _validate_snapshot(
        promoted, expected_revision=TARGET_REVISION, runtime_required=True
    )
    if candidate["business"] != promoted["business"]:
        raise ReleaseContractError(
            "Promoted database business evidence differs from the certified candidate"
        )


def verify_source_promoted_identity(source: Snapshot, promoted: Snapshot) -> None:
    source_identity = _validate_identity(source["identity"])
    promoted_identity = _validate_identity(promoted["identity"])
    if source_identity != promoted_identity:
        raise ReleaseContractError(
            "Promoted PostgreSQL identity is not the retained source identity"
        )


def _configured_database_snapshot(
    *,
    expected_revision: str,
    require_runtime_certificate: bool,
) -> Snapshot:
    """Connect using app settings while keeping all credentials out of evidence."""

    from app.core.config import Settings
    from app.db.session import Database

    maintenance_settings = Settings(database_read_only=True)
    if maintenance_settings.database_type != "postgres":
        raise ReleaseContractError("Release certification requires PostgreSQL settings")
    maintenance_database = Database(maintenance_settings)
    runtime_database: Any | None = None

    def runtime_hook(_target: Any) -> None:
        nonlocal runtime_database
        runtime_settings = Settings(
            database_type="postgres",
            database_host=maintenance_settings.database_host,
            database_port=maintenance_settings.database_port,
            database_name=maintenance_settings.database_name,
            database_user="caresync_release_probe",
            database_password=os.environ["CARESYNC_RELEASE_PROBE_PASSWORD"],
            database_read_only=True,
            enable_advanced_routes=False,
        )
        runtime_database = Database(runtime_settings)
        _assert_controlled_release_probe(runtime_database)
        if runtime_database.has_live_room_presence_safety_board() is not True:
            raise ReleaseContractError(
                "Runtime certificate rejected the live-room safety board"
            )
        if runtime_database.has_billing_ledger() is not True:
            raise ReleaseContractError(
                "Runtime certificate rejected the billing ledger"
            )

    try:
        with (
            maintenance_database.engine.connect().execution_options(
                isolation_level="REPEATABLE READ"
            ) as connection,
            connection.begin(),
        ):
            return collect_snapshot(
                connection,
                expected_revision=expected_revision,
                runtime_certificate_hook=runtime_hook
                if require_runtime_certificate
                else None,
            )
    finally:
        if runtime_database is not None:
            runtime_database.dispose()
        maintenance_database.dispose()


def _assert_controlled_release_probe(database: Any) -> None:
    """Prove controlled health uses only the DB-enforced non-writer identity."""

    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    with database.engine.connect() as connection:
        identity = connection.execute(
            text(
                "SELECT current_user, "
                "current_setting('default_transaction_read_only')"
            )
        ).one()
        if tuple(identity) != ("caresync_release_probe", "on"):
            raise ReleaseContractError(
                "Controlled runtime did not use the read-only release probe"
            )
        try:
            connection.execute(
                text("DELETE FROM public.alembic_version WHERE false")
            )
        except DBAPIError:
            connection.rollback()
        else:
            connection.rollback()
            raise ReleaseContractError(
                "Controlled release probe unexpectedly acquired business DML"
            )


def _collect_physical_online_attestation(
    connection: Any,
    *,
    rehearsed_source: Snapshot,
) -> dict[str, Any]:
    """Collect the rehearsal endpoint, writer fences and cluster-wide isolation."""

    from sqlalchemy import text

    role_rows = (
        connection.execute(
            text(
                "SELECT rolname, rolcanlogin "
                "FROM pg_catalog.pg_roles "
                "WHERE rolname IN "
                "('caresync_basic_app','caresync_transport_evidence_ingest') "
                "ORDER BY rolname"
            )
        )
        .mappings()
        .all()
    )
    writer_states = {
        row["rolname"]: "login" if bool(row["rolcanlogin"]) else "nologin"
        for row in role_rows
    }
    other_clients = connection.execute(
        text(
            "SELECT count(*) "
            "FROM pg_catalog.pg_stat_activity "
            "WHERE backend_type='client backend' "
            "AND pid<>pg_backend_pid()"
        )
    ).scalar_one()
    is_in_recovery = connection.execute(
        text("SELECT pg_catalog.pg_is_in_recovery()")
    ).scalar_one()
    identity = _validate_identity(rehearsed_source["identity"])
    attestation = {
        "endpoint": f"{identity['serverAddress']}:{identity['serverPort']}",
        "isInRecovery": bool(is_in_recovery),
        "writerRoleStates": writer_states,
        "otherClientSessions": int(other_clients),
    }
    return _validate_physical_online_attestation(
        attestation,
        rehearsed_source=rehearsed_source,
    )


def _configured_physical_rehearsal_inputs() -> tuple[Snapshot, dict[str, Any]]:
    """Capture source evidence and online isolation in one read-only transaction."""

    from app.core.config import Settings
    from app.db.session import Database

    settings = Settings(database_read_only=True)
    if settings.database_type != "postgres":
        raise ReleaseContractError("Release certification requires PostgreSQL settings")
    database = Database(settings)
    try:
        with (
            database.engine.connect().execution_options(
                isolation_level="REPEATABLE READ"
            ) as connection,
            connection.begin(),
        ):
            source = collect_snapshot(
                connection,
                expected_revision=SOURCE_REVISION,
            )
            attestation = _collect_physical_online_attestation(
                connection,
                rehearsed_source=source,
            )
            return source, attestation
    finally:
        database.dispose()


def _configured_runtime_state() -> dict[str, Any]:
    """Connect as owner plus restricted runtime for post-health certification."""

    from app.core.config import Settings
    from app.db.session import Database

    maintenance_settings = Settings(database_read_only=True)
    if maintenance_settings.database_type != "postgres":
        raise ReleaseContractError("Release finalization requires PostgreSQL settings")
    maintenance_database = Database(maintenance_settings)
    runtime_database: Any | None = None

    def runtime_hook(_target: Any) -> None:
        nonlocal runtime_database
        runtime_settings = Settings(
            database_type="postgres",
            database_host=maintenance_settings.database_host,
            database_port=maintenance_settings.database_port,
            database_name=maintenance_settings.database_name,
            database_user="caresync_release_probe",
            database_password=os.environ["CARESYNC_RELEASE_PROBE_PASSWORD"],
            database_read_only=True,
            enable_advanced_routes=False,
        )
        runtime_database = Database(runtime_settings)
        _assert_controlled_release_probe(runtime_database)
        if runtime_database.has_live_room_presence_safety_board() is not True:
            raise ReleaseContractError(
                "Runtime certificate rejected the live-room safety board"
            )
        if runtime_database.has_billing_ledger() is not True:
            raise ReleaseContractError(
                "Runtime certificate rejected the billing ledger"
            )

    try:
        with (
            maintenance_database.engine.connect().execution_options(
                isolation_level="REPEATABLE READ"
            ) as connection,
            connection.begin(),
        ):
            return collect_runtime_state(
                connection,
                runtime_certificate_hook=runtime_hook,
            )
    finally:
        if runtime_database is not None:
            runtime_database.dispose()
        maintenance_database.dispose()


def _validate_restore_receipt(
    payload: Mapping[str, Any],
    *,
    expected_backup_sha: str | None = None,
) -> None:
    if payload.get("format") != "caresync-restore-verification-v1":
        raise ReleaseContractError("Database restore receipt has the wrong format")
    if payload.get("alembicRevisions") != [SOURCE_REVISION]:
        raise ReleaseContractError("Database restore receipt is not exact 0039")
    backup_sha = payload.get("backupSha256")
    if not isinstance(backup_sha, str) or not _SHA256.fullmatch(backup_sha):
        raise ReleaseContractError("Database restore receipt has no backup SHA-256")
    if expected_backup_sha is not None and backup_sha != expected_backup_sha:
        raise ReleaseContractError(
            "Database restore receipt names a different backup SHA-256"
        )
    attestation = payload.get("strongTargetAttestation")
    if not isinstance(attestation, dict) or attestation.get("performed") is not True:
        raise ReleaseContractError(
            "Database restore receipt lacks strong target attestation"
        )
    required = {
        "roleName",
        "databaseName",
        "serverAddress",
        "serverPort",
        "dataDirectory",
        "systemIdentifier",
        "otherClientSessions",
        "targetWasEmpty",
        "alembicRevisions",
        "tableCounts",
    }
    if not required.issubset(attestation):
        raise ReleaseContractError(
            "Database restore receipt lacks PostgreSQL identity fields"
        )
    string_fields = (
        "roleName",
        "databaseName",
        "serverAddress",
        "dataDirectory",
        "systemIdentifier",
    )
    if any(
        not isinstance(attestation[field], str) or not attestation[field]
        for field in string_fields
    ):
        raise ReleaseContractError(
            "Database restore receipt has an invalid PostgreSQL identity"
        )
    if (
        isinstance(attestation["serverPort"], bool)
        or not isinstance(attestation["serverPort"], int)
        or not 1 <= attestation["serverPort"] <= 65535
        or isinstance(attestation["otherClientSessions"], bool)
        or attestation["otherClientSessions"] != 0
    ):
        raise ReleaseContractError("Disposable restore had another client session")
    pre_restore_counts = attestation["tableCounts"]
    if (
        attestation["targetWasEmpty"] is not True
        or attestation["alembicRevisions"] != [SOURCE_REVISION]
        or not isinstance(pre_restore_counts, dict)
        or not pre_restore_counts
        or pre_restore_counts.get("alembic_version") != 1
        or any(
            not isinstance(name, str)
            or not name
            or isinstance(count, bool)
            or not isinstance(count, int)
            or count < 0
            or (name != "alembic_version" and count != 0)
            for name, count in pre_restore_counts.items()
        )
    ):
        raise ReleaseContractError(
            "Disposable restore target was not attested as completely empty"
        )


def _validate_clone_certificate(payload: Any) -> dict[str, Any]:
    certificate = _require_shape(
        payload,
        {
            "format",
            "phase",
            "certificateId",
            "createdAt",
            "restoreReceipt",
            "candidate",
        },
        label="clone certificate",
    )
    if (
        certificate["format"] != CLONE_CERTIFICATE_FORMAT
        or certificate["phase"] != "clone"
        or not isinstance(certificate["certificateId"], str)
        or not certificate["certificateId"]
        or not isinstance(certificate["createdAt"], str)
    ):
        raise ReleaseContractError("clone certificate metadata is invalid")
    _validate_artifact_binding(
        certificate["restoreReceipt"],
        label="clone restore receipt binding",
    )
    candidate = _validate_snapshot(
        certificate["candidate"],
        expected_revision=TARGET_REVISION,
        runtime_required=True,
    )
    return {**certificate, "candidate": candidate}


def create_clone_certificate(
    *,
    restore_receipt_path: Path,
    output_path: Path,
    candidate_snapshot: Snapshot,
) -> dict[str, Any]:
    restore_payload = read_private_json(
        restore_receipt_path,
        label="database restore receipt",
    )
    _validate_restore_receipt(restore_payload)
    _validate_snapshot(
        candidate_snapshot,
        expected_revision=TARGET_REVISION,
        runtime_required=True,
    )
    attestation = restore_payload["strongTargetAttestation"]
    identity = candidate_snapshot["identity"]
    comparisons = {
        "roleName": "roleName",
        "databaseName": "databaseName",
        "serverAddress": "serverAddress",
        "serverPort": "serverPort",
        "dataDirectory": "dataDirectory",
        "systemIdentifier": "systemIdentifier",
    }
    if any(identity[left] != attestation[right] for left, right in comparisons.items()):
        raise ReleaseContractError(
            "Candidate PostgreSQL identity differs from restored target attestation"
        )
    certificate = {
        "format": CLONE_CERTIFICATE_FORMAT,
        "phase": "clone",
        "certificateId": str(uuid4()),
        "createdAt": _utc_now(),
        "restoreReceipt": bind_private_artifact(
            restore_receipt_path,
            label="database restore receipt",
        ),
        "candidate": candidate_snapshot,
    }
    _validate_clone_certificate(certificate)
    write_private_json_no_clobber(output_path, certificate)
    return certificate


_PAYLOAD_KEYS = {
    "format",
    "releaseId",
    "generatedAt",
    "sourceRevision",
    "targetRevision",
    "source",
    "candidate",
    "artifacts",
}


def _validate_release_payload(payload: Any) -> dict[str, Any]:
    value = _require_shape(payload, _PAYLOAD_KEYS, label="release payload")
    if (
        value["format"] != RELEASE_PAYLOAD_FORMAT
        or not isinstance(value["releaseId"], str)
        or not value["releaseId"]
        or not isinstance(value["generatedAt"], str)
        or value["sourceRevision"] != SOURCE_REVISION
        or value["targetRevision"] != TARGET_REVISION
    ):
        raise ReleaseContractError("release payload metadata is invalid")
    _validate_snapshot(
        value["source"],
        expected_revision=SOURCE_REVISION,
        runtime_required=False,
    )
    _validate_snapshot(
        value["candidate"],
        expected_revision=TARGET_REVISION,
        runtime_required=True,
    )
    _validate_payload_artifact_bindings(value["artifacts"])
    return value


_CANDIDATE_KEYS = {
    "format",
    "phase",
    "releaseId",
    "createdAt",
    "sourceRevision",
    "targetRevision",
    "source",
    "candidate",
    "artifacts",
}


def _validate_candidate_receipt(payload: Any) -> dict[str, Any]:
    receipt = _require_shape(payload, _CANDIDATE_KEYS, label="candidate receipt")
    if (
        receipt["format"] != CANDIDATE_RECEIPT_FORMAT
        or receipt["phase"] != "candidate"
        or not isinstance(receipt["releaseId"], str)
        or not receipt["releaseId"]
        or not isinstance(receipt["createdAt"], str)
        or receipt["sourceRevision"] != SOURCE_REVISION
        or receipt["targetRevision"] != TARGET_REVISION
    ):
        raise ReleaseContractError("candidate receipt metadata is invalid")
    source = _validate_snapshot(
        receipt["source"],
        expected_revision=SOURCE_REVISION,
        runtime_required=False,
    )
    candidate = _validate_snapshot(
        receipt["candidate"],
        expected_revision=TARGET_REVISION,
        runtime_required=True,
    )
    verify_source_candidate(source, candidate)
    _validate_artifact_bindings(receipt["artifacts"], include_generated=True)
    return receipt


def _parse_backup_manifest(path: Path) -> dict[str, Any]:
    payload = read_private_json(path, label="backup manifest")
    if (
        payload.get("format") != "caresync-logical-backup-v2"
        or not isinstance(payload.get("backup"), str)
        or not isinstance(payload.get("sha256Compressed"), str)
        or not _SHA256.fullmatch(payload["sha256Compressed"])
    ):
        raise ReleaseContractError("Backup manifest is unsupported")
    return payload


def create_candidate_receipt(
    *,
    source_snapshot: Snapshot,
    clone_certificate_path: Path,
    artifact_paths: Mapping[str, Path],
    release_payload_path: Path,
    receipt_path: Path,
) -> dict[str, Any]:
    clone_payload = read_private_json(
        clone_certificate_path,
        label="clone certificate",
    )
    clone = _validate_clone_certificate(clone_payload)
    candidate_snapshot = clone["candidate"]
    verify_source_candidate(source_snapshot, candidate_snapshot)

    caller_bindings = bind_artifacts(artifact_paths)
    restore_payload = read_private_json(
        artifact_paths["database_restore_receipt"],
        label="database restore receipt",
    )
    backup_manifest = _parse_backup_manifest(artifact_paths["backup_manifest"])
    backup_binding = caller_bindings["backup"]
    if (
        backup_manifest["backup"] != backup_binding["name"]
        or backup_manifest["sha256Compressed"] != backup_binding["sha256"]
    ):
        raise ReleaseContractError("Backup manifest names a different backup")
    _validate_restore_receipt(
        restore_payload,
        expected_backup_sha=backup_binding["sha256"],
    )
    verify_physical_rehearsal_receipt(
        rehearsal_receipt_path=artifact_paths["physical_rehearsal_receipt"],
        rehearsal_observation_path=artifact_paths[
            "physical_rehearsal_observation"
        ],
        physical_backup_manifest_path=artifact_paths["physical_backup_manifest"],
        physical_backup_inventory_path=artifact_paths[
            "physical_backup_inventory"
        ],
        retained_identity_path=artifact_paths["retained_identity"],
        expected_source_snapshot=source_snapshot,
    )
    verify_artifact_binding(
        artifact_paths["database_restore_receipt"],
        clone["restoreReceipt"],
        label="database restore receipt",
    )

    release_id = str(uuid4())
    payload_artifacts = {
        **caller_bindings,
        "clone_certificate": bind_private_artifact(
            clone_certificate_path,
            label="clone certificate",
        ),
    }
    release_payload = {
        "format": RELEASE_PAYLOAD_FORMAT,
        "releaseId": release_id,
        "generatedAt": _utc_now(),
        "sourceRevision": SOURCE_REVISION,
        "targetRevision": TARGET_REVISION,
        "source": source_snapshot,
        "candidate": candidate_snapshot,
        "artifacts": payload_artifacts,
    }
    _validate_release_payload(release_payload)
    if os.path.lexists(_absolute_lexical(receipt_path)):
        raise ReleaseContractError(
            f"Refusing to replace existing release receipt {receipt_path}"
        )
    write_private_json_no_clobber(release_payload_path, release_payload)
    all_bindings = {
        **payload_artifacts,
        "release_payload": bind_private_artifact(
            release_payload_path,
            label="release payload",
        ),
    }
    receipt = {
        "format": CANDIDATE_RECEIPT_FORMAT,
        "phase": "candidate",
        "releaseId": release_id,
        "createdAt": _utc_now(),
        "sourceRevision": SOURCE_REVISION,
        "targetRevision": TARGET_REVISION,
        "source": source_snapshot,
        "candidate": candidate_snapshot,
        "artifacts": all_bindings,
    }
    _validate_candidate_receipt(receipt)
    write_private_json_no_clobber(receipt_path, receipt)
    return receipt


def _expected_all_artifact_paths(
    *,
    caller_paths: Mapping[str, Path],
    clone_certificate_path: Path,
    release_payload_path: Path,
) -> dict[str, Path]:
    validate_artifact_names(set(caller_paths))
    return {
        **caller_paths,
        "clone_certificate": clone_certificate_path,
        "release_payload": release_payload_path,
    }


def verify_candidate_receipt(
    *,
    receipt_path: Path,
    clone_certificate_path: Path,
    release_payload_path: Path,
    artifact_paths: Mapping[str, Path],
) -> dict[str, Any]:
    receipt = _validate_candidate_receipt(
        read_private_json(receipt_path, label="candidate receipt")
    )
    all_paths = _expected_all_artifact_paths(
        caller_paths=artifact_paths,
        clone_certificate_path=clone_certificate_path,
        release_payload_path=release_payload_path,
    )
    if set(all_paths) != set(receipt["artifacts"]):
        raise ReleaseContractError("candidate receipt artifact inventory differs")
    for name, path in all_paths.items():
        verify_artifact_binding(
            path,
            receipt["artifacts"][name],
            label=f"artifact {name}",
        )
    release_payload = _validate_release_payload(
        read_private_json(release_payload_path, label="release payload")
    )
    if (
        release_payload["releaseId"] != receipt["releaseId"]
        or release_payload["source"] != receipt["source"]
        or release_payload["candidate"] != receipt["candidate"]
        or release_payload["artifacts"]
        != {
            name: binding
            for name, binding in receipt["artifacts"].items()
            if name != "release_payload"
        }
    ):
        raise ReleaseContractError("release payload differs from candidate receipt")
    clone = _validate_clone_certificate(
        read_private_json(clone_certificate_path, label="clone certificate")
    )
    if clone["candidate"] != receipt["candidate"]:
        raise ReleaseContractError("clone certificate differs from candidate receipt")
    verify_physical_rehearsal_receipt(
        rehearsal_receipt_path=artifact_paths["physical_rehearsal_receipt"],
        rehearsal_observation_path=artifact_paths[
            "physical_rehearsal_observation"
        ],
        physical_backup_manifest_path=artifact_paths["physical_backup_manifest"],
        physical_backup_inventory_path=artifact_paths[
            "physical_backup_inventory"
        ],
        retained_identity_path=artifact_paths["retained_identity"],
        expected_source_snapshot=receipt["source"],
    )
    return receipt


_COMMIT_KEYS = {
    "format",
    "phase",
    "releaseId",
    "committedAt",
    "sourceRevision",
    "targetRevision",
    "candidateReceipt",
    "source",
    "candidate",
    "promoted",
    "artifacts",
}


def _validate_commit_receipt(payload: Any) -> dict[str, Any]:
    receipt = _require_shape(payload, _COMMIT_KEYS, label="commit receipt")
    if (
        receipt["format"] != COMMIT_RECEIPT_FORMAT
        or receipt["phase"] != "committed"
        or not isinstance(receipt["releaseId"], str)
        or not receipt["releaseId"]
        or not isinstance(receipt["committedAt"], str)
        or receipt["sourceRevision"] != SOURCE_REVISION
        or receipt["targetRevision"] != TARGET_REVISION
    ):
        raise ReleaseContractError("commit receipt metadata is invalid")
    _validate_artifact_binding(
        receipt["candidateReceipt"],
        label="candidate receipt binding",
    )
    source = _validate_snapshot(
        receipt["source"],
        expected_revision=SOURCE_REVISION,
        runtime_required=False,
    )
    candidate = _validate_snapshot(
        receipt["candidate"],
        expected_revision=TARGET_REVISION,
        runtime_required=True,
    )
    promoted = _validate_snapshot(
        receipt["promoted"],
        expected_revision=TARGET_REVISION,
        runtime_required=True,
    )
    verify_source_candidate(source, candidate)
    verify_candidate_promoted(candidate, promoted)
    verify_source_promoted_identity(source, promoted)
    _validate_artifact_bindings(receipt["artifacts"], include_generated=True)
    return receipt


def create_commit_receipt(
    *,
    candidate_receipt_path: Path,
    clone_certificate_path: Path,
    release_payload_path: Path,
    artifact_paths: Mapping[str, Path],
    promoted_snapshot: Snapshot,
    receipt_path: Path,
) -> dict[str, Any]:
    candidate_receipt = verify_candidate_receipt(
        receipt_path=candidate_receipt_path,
        clone_certificate_path=clone_certificate_path,
        release_payload_path=release_payload_path,
        artifact_paths=artifact_paths,
    )
    verify_candidate_promoted(candidate_receipt["candidate"], promoted_snapshot)
    verify_source_promoted_identity(candidate_receipt["source"], promoted_snapshot)
    receipt = {
        "format": COMMIT_RECEIPT_FORMAT,
        "phase": "committed",
        "releaseId": candidate_receipt["releaseId"],
        "committedAt": _utc_now(),
        "sourceRevision": SOURCE_REVISION,
        "targetRevision": TARGET_REVISION,
        "candidateReceipt": bind_private_artifact(
            candidate_receipt_path,
            label="candidate receipt",
        ),
        "source": candidate_receipt["source"],
        "candidate": candidate_receipt["candidate"],
        "promoted": promoted_snapshot,
        "artifacts": candidate_receipt["artifacts"],
    }
    _validate_commit_receipt(receipt)
    write_private_json_no_clobber(receipt_path, receipt)
    return receipt


def verify_commit_receipt(
    *,
    commit_receipt_path: Path,
    candidate_receipt_path: Path,
    clone_certificate_path: Path,
    release_payload_path: Path,
    artifact_paths: Mapping[str, Path],
) -> dict[str, Any]:
    candidate = verify_candidate_receipt(
        receipt_path=candidate_receipt_path,
        clone_certificate_path=clone_certificate_path,
        release_payload_path=release_payload_path,
        artifact_paths=artifact_paths,
    )
    commit = _validate_commit_receipt(
        read_private_json(commit_receipt_path, label="commit receipt")
    )
    verify_artifact_binding(
        candidate_receipt_path,
        commit["candidateReceipt"],
        label="candidate receipt",
    )
    if (
        commit["releaseId"] != candidate["releaseId"]
        or commit["source"] != candidate["source"]
        or commit["candidate"] != candidate["candidate"]
        or commit["artifacts"] != candidate["artifacts"]
    ):
        raise ReleaseContractError("commit receipt differs from candidate receipt")
    return commit


def verify_live_commit_state(
    *,
    current_promoted_snapshot: Snapshot,
    commit_receipt_path: Path,
    candidate_receipt_path: Path,
    clone_certificate_path: Path,
    release_payload_path: Path,
    artifact_paths: Mapping[str, Path],
) -> dict[str, Any]:
    """Reopen a commit and prove the currently configured live 0043 state."""

    commit = verify_commit_receipt(
        commit_receipt_path=commit_receipt_path,
        candidate_receipt_path=candidate_receipt_path,
        clone_certificate_path=clone_certificate_path,
        release_payload_path=release_payload_path,
        artifact_paths=artifact_paths,
    )
    verify_candidate_promoted(commit["candidate"], current_promoted_snapshot)
    verify_source_promoted_identity(commit["source"], current_promoted_snapshot)
    if current_promoted_snapshot != commit["promoted"]:
        raise ReleaseContractError(
            "Current live 0043 snapshot differs from the commit receipt"
        )
    return commit


def certify_source_resume(
    *,
    current_source_snapshot: Snapshot,
    candidate_receipt_path: Path,
    clone_certificate_path: Path,
    release_payload_path: Path,
    artifact_paths: Mapping[str, Path],
) -> dict[str, Any]:
    candidate = verify_candidate_receipt(
        receipt_path=candidate_receipt_path,
        clone_certificate_path=clone_certificate_path,
        release_payload_path=release_payload_path,
        artifact_paths=artifact_paths,
    )
    _validate_snapshot(
        current_source_snapshot,
        expected_revision=SOURCE_REVISION,
        runtime_required=False,
    )
    if current_source_snapshot != candidate["source"]:
        raise ReleaseContractError(
            "Current 0039 database is not the source captured by the candidate receipt"
        )
    return candidate


_RESUME_AUTHORIZATION_KEYS = {
    "format",
    "phase",
    "releaseId",
    "authorizedAt",
    "sourceRevision",
    "targetRevision",
    "candidateReceipt",
    "source",
    "artifacts",
}


def _validate_resume_authorization(payload: Any) -> dict[str, Any]:
    authorization = _require_shape(
        payload,
        _RESUME_AUTHORIZATION_KEYS,
        label="0039 resume authorization",
    )
    if (
        authorization["format"] != RESUME_AUTHORIZATION_FORMAT
        or authorization["phase"] != "resume_0039"
        or not isinstance(authorization["releaseId"], str)
        or not authorization["releaseId"]
        or not isinstance(authorization["authorizedAt"], str)
        or authorization["sourceRevision"] != SOURCE_REVISION
        or authorization["targetRevision"] != TARGET_REVISION
    ):
        raise ReleaseContractError("0039 resume authorization metadata is invalid")
    _validate_artifact_binding(
        authorization["candidateReceipt"],
        label="candidate receipt binding",
    )
    _validate_snapshot(
        authorization["source"],
        expected_revision=SOURCE_REVISION,
        runtime_required=False,
    )
    _validate_artifact_bindings(
        authorization["artifacts"],
        include_generated=True,
    )
    return authorization


def create_resume_authorization(
    *,
    current_source_snapshot: Snapshot,
    candidate_receipt_path: Path,
    clone_certificate_path: Path,
    release_payload_path: Path,
    artifact_paths: Mapping[str, Path],
    authorization_path: Path,
) -> dict[str, Any]:
    """Authorize one exact, still-unmodified 0039 release retry."""

    candidate = certify_source_resume(
        current_source_snapshot=current_source_snapshot,
        candidate_receipt_path=candidate_receipt_path,
        clone_certificate_path=clone_certificate_path,
        release_payload_path=release_payload_path,
        artifact_paths=artifact_paths,
    )
    authorization = {
        "format": RESUME_AUTHORIZATION_FORMAT,
        "phase": "resume_0039",
        "releaseId": candidate["releaseId"],
        "authorizedAt": _utc_now(),
        "sourceRevision": SOURCE_REVISION,
        "targetRevision": TARGET_REVISION,
        "candidateReceipt": bind_private_artifact(
            candidate_receipt_path,
            label="candidate receipt",
        ),
        "source": candidate["source"],
        "artifacts": candidate["artifacts"],
    }
    _validate_resume_authorization(authorization)
    write_private_json_no_clobber(authorization_path, authorization)
    return authorization


def verify_resume_authorization(
    *,
    authorization_path: Path,
    current_source_snapshot: Snapshot,
    candidate_receipt_path: Path,
    clone_certificate_path: Path,
    release_payload_path: Path,
    artifact_paths: Mapping[str, Path],
) -> dict[str, Any]:
    """Independently re-prove an authorization against current 0039 state."""

    candidate = certify_source_resume(
        current_source_snapshot=current_source_snapshot,
        candidate_receipt_path=candidate_receipt_path,
        clone_certificate_path=clone_certificate_path,
        release_payload_path=release_payload_path,
        artifact_paths=artifact_paths,
    )
    authorization = _validate_resume_authorization(
        read_private_json(
            authorization_path,
            label="0039 resume authorization",
        )
    )
    verify_artifact_binding(
        candidate_receipt_path,
        authorization["candidateReceipt"],
        label="candidate receipt",
    )
    if (
        authorization["releaseId"] != candidate["releaseId"]
        or authorization["source"] != current_source_snapshot
        or authorization["artifacts"] != candidate["artifacts"]
    ):
        raise ReleaseContractError(
            "0039 resume authorization differs from current release evidence"
        )
    return authorization


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        request: Any,
        file_pointer: Any,
        code: int,
        message: str,
        headers: Any,
        new_url: str,
    ) -> None:
        del request, file_pointer, code, message, headers, new_url
        raise ReleaseContractError("Release health probe refused an HTTP redirect")


def collect_local_health_evidence() -> dict[str, Any]:
    """Probe the fixed loopback API and frontend without proxies or redirects."""

    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        _NoRedirect(),
    )

    def fetch(url: str) -> tuple[bytes, str]:
        request = urllib.request.Request(  # noqa: S310 - fixed loopback URLs only.
            url,
            headers={"Accept": "application/json,text/html"},
            method="GET",
        )
        try:
            with opener.open(request, timeout=5) as response:  # noqa: S310
                if response.status != 200 or response.geturl() != url:
                    raise ReleaseContractError(
                        "Release health probe returned an unexpected response"
                    )
                body = response.read(1024 * 1024 + 1)
                if len(body) > 1024 * 1024:
                    raise ReleaseContractError(
                        "Release health response is unexpectedly large"
                    )
                return body, response.headers.get_content_type()
        except (OSError, urllib.error.URLError) as error:
            raise ReleaseContractError(
                "Release health probe could not reach the local service"
            ) from error

    api_url = "http://127.0.0.1:3002/api/v1/health"
    api_bytes, api_content_type = fetch(api_url)
    if api_content_type != "application/json":
        raise ReleaseContractError("CareSync API health did not return JSON")
    try:
        api = json.loads(
            api_bytes.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReleaseContractError("CareSync API health JSON is invalid") from error
    if not isinstance(api, dict) or not isinstance(api.get("database"), dict):
        raise ReleaseContractError("CareSync API health response has the wrong shape")
    database = api["database"]
    if (
        api.get("status") != "ok"
        or database.get("connected") is not True
        or database.get("integrity") not in {"ok", "not_applicable"}
        or database.get("database_name") != "caresync"
        or not isinstance(api.get("service"), str)
        or not api["service"]
        or not isinstance(api.get("version"), str)
        or not api["version"]
    ):
        raise ReleaseContractError("CareSync API did not certify healthy database use")

    frontend_url = "http://127.0.0.1:5174/"
    frontend, frontend_content_type = fetch(frontend_url)
    if frontend_content_type != "text/html":
        raise ReleaseContractError("CareSync frontend did not return HTML")
    try:
        frontend_text = frontend.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ReleaseContractError("CareSync frontend HTML is not UTF-8") from error
    if 'id="root"' not in frontend_text or "<title>CareSync" not in frontend_text:
        raise ReleaseContractError(
            "Port 5174 is not serving the CareSync application shell"
        )
    return {
        "api": {
            "status": "ok",
            "service": api["service"],
            "version": api["version"],
            "databaseName": "caresync",
            "databaseIntegrity": database["integrity"],
        },
        "frontend": {
            "status": "ok",
            "sha256Body": hashlib.sha256(frontend).hexdigest(),
        },
    }


def _validate_health_evidence(value: Any) -> dict[str, Any]:
    health = _require_shape(value, {"api", "frontend"}, label="health evidence")
    api = _require_shape(
        health["api"],
        {
            "status",
            "service",
            "version",
            "databaseName",
            "databaseIntegrity",
        },
        label="API health evidence",
    )
    frontend = _require_shape(
        health["frontend"],
        {"status", "sha256Body"},
        label="frontend health evidence",
    )
    if (
        api["status"] != "ok"
        or not isinstance(api["service"], str)
        or not api["service"]
        or not isinstance(api["version"], str)
        or not api["version"]
        or api["databaseName"] != "caresync"
        or api["databaseIntegrity"] not in {"ok", "not_applicable"}
        or frontend["status"] != "ok"
        or not isinstance(frontend["sha256Body"], str)
        or not _SHA256.fullmatch(frontend["sha256Body"])
    ):
        raise ReleaseContractError("post-start health evidence is invalid")
    return health


_FINALIZATION_KEYS = {
    "format",
    "phase",
    "releaseId",
    "finalizedAt",
    "sourceRevision",
    "targetRevision",
    "commitReceipt",
    "live",
    "artifacts",
    "health",
}


def _validate_finalization_receipt(payload: Any) -> dict[str, Any]:
    receipt = _require_shape(
        payload,
        _FINALIZATION_KEYS,
        label="release finalization receipt",
    )
    if (
        receipt["format"] != FINALIZATION_RECEIPT_FORMAT
        or receipt["phase"] != "healthy"
        or not isinstance(receipt["releaseId"], str)
        or not receipt["releaseId"]
        or not isinstance(receipt["finalizedAt"], str)
        or receipt["sourceRevision"] != SOURCE_REVISION
        or receipt["targetRevision"] != TARGET_REVISION
    ):
        raise ReleaseContractError("release finalization metadata is invalid")
    _validate_artifact_binding(
        receipt["commitReceipt"],
        label="commit receipt binding",
    )
    _validate_runtime_state(receipt["live"])
    _validate_artifact_bindings(receipt["artifacts"], include_generated=True)
    _validate_health_evidence(receipt["health"])
    return receipt


def create_finalization_receipt(
    *,
    commit_receipt_path: Path,
    candidate_receipt_path: Path,
    clone_certificate_path: Path,
    release_payload_path: Path,
    artifact_paths: Mapping[str, Path],
    current_live_state: Mapping[str, Any],
    health_evidence: Mapping[str, Any],
    receipt_path: Path,
) -> dict[str, Any]:
    """Seal an already committed release only after local services are healthy."""

    commit = verify_commit_receipt(
        commit_receipt_path=commit_receipt_path,
        candidate_receipt_path=candidate_receipt_path,
        clone_certificate_path=clone_certificate_path,
        release_payload_path=release_payload_path,
        artifact_paths=artifact_paths,
    )
    live = _validate_runtime_state(current_live_state)
    if commit["source"]["identity"] != live["identity"]:
        raise ReleaseContractError(
            "Post-health PostgreSQL identity is not the retained source identity"
        )
    _validate_health_evidence(health_evidence)
    receipt = {
        "format": FINALIZATION_RECEIPT_FORMAT,
        "phase": "healthy",
        "releaseId": commit["releaseId"],
        "finalizedAt": _utc_now(),
        "sourceRevision": SOURCE_REVISION,
        "targetRevision": TARGET_REVISION,
        "commitReceipt": bind_private_artifact(
            commit_receipt_path,
            label="commit receipt",
        ),
        "live": live,
        "artifacts": commit["artifacts"],
        "health": dict(health_evidence),
    }
    _validate_finalization_receipt(receipt)
    write_private_json_no_clobber(receipt_path, receipt)
    return receipt


def verify_finalization_receipt(
    *,
    finalization_receipt_path: Path,
    commit_receipt_path: Path,
    candidate_receipt_path: Path,
    clone_certificate_path: Path,
    release_payload_path: Path,
    artifact_paths: Mapping[str, Path],
) -> dict[str, Any]:
    commit = verify_commit_receipt(
        commit_receipt_path=commit_receipt_path,
        candidate_receipt_path=candidate_receipt_path,
        clone_certificate_path=clone_certificate_path,
        release_payload_path=release_payload_path,
        artifact_paths=artifact_paths,
    )
    finalization = _validate_finalization_receipt(
        read_private_json(
            finalization_receipt_path,
            label="release finalization receipt",
        )
    )
    verify_artifact_binding(
        commit_receipt_path,
        finalization["commitReceipt"],
        label="commit receipt",
    )
    if (
        finalization["releaseId"] != commit["releaseId"]
        or finalization["live"]["identity"] != commit["source"]["identity"]
        or finalization["artifacts"] != commit["artifacts"]
    ):
        raise ReleaseContractError(
            "release finalization differs from the committed release"
        )
    return finalization


def _artifact_argument(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("artifact must be NAME=PATH")
    name, raw_path = value.split("=", 1)
    if not name or not raw_path:
        raise argparse.ArgumentTypeError("artifact must be NAME=PATH")
    return name, Path(raw_path)


def _artifact_map(values: Sequence[tuple[str, Path]]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for name, path in values:
        if name in result:
            raise ReleaseContractError(f"Artifact {name!r} was supplied twice")
        result[name] = path
    validate_artifact_names(set(result))
    return result


def _add_verification_inputs(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--candidate-receipt", type=Path, required=True)
    parser.add_argument("--clone-certificate", type=Path, required=True)
    parser.add_argument("--release-payload", type=Path, required=True)
    parser.add_argument(
        "--artifact",
        action="append",
        default=[],
        type=_artifact_argument,
        metavar="NAME=PATH",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Certify the two-phase CareSync Basic 0039 to 0043 release"
    )
    commands = parser.add_subparsers(dest="command", required=True)

    clone = commands.add_parser("certify-clone")
    clone.add_argument("--restore-receipt", type=Path, required=True)
    clone.add_argument("--output", type=Path, required=True)

    inventory = commands.add_parser("inventory-physical-backup")
    inventory.add_argument("--pgdata", type=Path, required=True)
    inventory.add_argument("--output", type=Path, required=True)

    verify_inventory = commands.add_parser("verify-physical-backup-inventory")
    verify_inventory.add_argument("--pgdata", type=Path, required=True)
    verify_inventory.add_argument("--inventory", type=Path, required=True)

    atomic_rename = commands.add_parser("atomic-rename-no-replace")
    atomic_rename.add_argument("--source", type=Path, required=True)
    atomic_rename.add_argument("--destination", type=Path, required=True)

    durable_publish = commands.add_parser("durable-publish-private-file")
    durable_publish.add_argument("--source", type=Path, required=True)
    durable_publish.add_argument("--destination", type=Path, required=True)

    durable_replace = commands.add_parser("durable-replace-private-file")
    durable_replace.add_argument("--source", type=Path, required=True)
    durable_replace.add_argument("--destination", type=Path, required=True)

    durable_remove = commands.add_parser("durable-remove-private-file")
    durable_remove.add_argument("--path", type=Path, required=True)

    durable_fence = commands.add_parser("durable-rename-private-fence")
    durable_fence.add_argument("--source", type=Path, required=True)
    durable_fence.add_argument("--destination", type=Path, required=True)

    ensure_directory = commands.add_parser("ensure-private-directory")
    ensure_directory.add_argument("--path", type=Path, required=True)

    durability_file = commands.add_parser("durability-barrier-private-file")
    durability_file.add_argument("--path", type=Path, required=True)

    validate_tree = commands.add_parser("validate-private-tree")
    validate_tree.add_argument("--path", type=Path, required=True)

    durability_barrier = commands.add_parser("durability-barrier-private-tree")
    durability_barrier.add_argument("--path", type=Path, required=True)

    observe_rehearsal = commands.add_parser("observe-physical-rehearsal")
    observe_rehearsal.add_argument(
        "--physical-backup-manifest",
        type=Path,
        required=True,
    )
    observe_rehearsal.add_argument(
        "--physical-backup-inventory",
        type=Path,
        required=True,
    )
    observe_rehearsal.add_argument(
        "--retained-identity", type=Path, required=True
    )
    observe_rehearsal.add_argument("--observation", type=Path, required=True)

    rehearsal = commands.add_parser("certify-physical-rehearsal")
    rehearsal.add_argument("--observation", type=Path, required=True)
    rehearsal.add_argument("--rehearsal-pgdata", type=Path, required=True)
    rehearsal.add_argument("--physical-backup-manifest", type=Path, required=True)
    rehearsal.add_argument("--physical-backup-inventory", type=Path, required=True)
    rehearsal.add_argument("--retained-identity", type=Path, required=True)
    rehearsal.add_argument("--receipt", type=Path, required=True)

    verify_rehearsal = commands.add_parser("verify-physical-rehearsal")
    verify_rehearsal.add_argument("--observation", type=Path, required=True)
    verify_rehearsal.add_argument(
        "--physical-backup-manifest",
        type=Path,
        required=True,
    )
    verify_rehearsal.add_argument(
        "--physical-backup-inventory",
        type=Path,
        required=True,
    )
    verify_rehearsal.add_argument("--retained-identity", type=Path, required=True)
    verify_rehearsal.add_argument("--receipt", type=Path, required=True)

    prepare = commands.add_parser("prepare")
    prepare.add_argument("--clone-certificate", type=Path, required=True)
    prepare.add_argument("--release-payload", type=Path, required=True)
    prepare.add_argument("--receipt", type=Path, required=True)
    prepare.add_argument(
        "--artifact",
        action="append",
        default=[],
        type=_artifact_argument,
        metavar="NAME=PATH",
    )

    verify_prepare = commands.add_parser("verify-prepare-receipt")
    verify_prepare.add_argument(
        "--receipt", dest="candidate_receipt", type=Path, required=True
    )
    verify_prepare.add_argument("--clone-certificate", type=Path, required=True)
    verify_prepare.add_argument("--release-payload", type=Path, required=True)
    verify_prepare.add_argument(
        "--artifact",
        action="append",
        default=[],
        type=_artifact_argument,
        metavar="NAME=PATH",
    )

    live = commands.add_parser("certify-live")
    _add_verification_inputs(live)
    live.add_argument("--receipt", type=Path, required=True)

    verify_commit = commands.add_parser("verify-commit-receipt")
    _add_verification_inputs(verify_commit)
    verify_commit.add_argument(
        "--receipt", dest="commit_receipt", type=Path, required=True
    )

    verify_live = commands.add_parser("verify-live-commit")
    _add_verification_inputs(verify_live)
    verify_live.add_argument("--commit-receipt", type=Path, required=True)

    finalize = commands.add_parser("finalize-live")
    _add_verification_inputs(finalize)
    finalize.add_argument("--commit-receipt", type=Path, required=True)
    finalize.add_argument("--receipt", type=Path, required=True)

    verify_finalization = commands.add_parser("verify-finalization-receipt")
    _add_verification_inputs(verify_finalization)
    verify_finalization.add_argument("--commit-receipt", type=Path, required=True)
    verify_finalization.add_argument(
        "--receipt",
        dest="finalization_receipt",
        type=Path,
        required=True,
    )

    resume = commands.add_parser("certify-resume-0039")
    _add_verification_inputs(resume)
    resume.add_argument("--authorization", type=Path, required=True)

    verify_resume = commands.add_parser("verify-resume-authorization")
    _add_verification_inputs(verify_resume)
    verify_resume.add_argument("--authorization", type=Path, required=True)
    return parser


def _success(command: str, identifier: str) -> None:
    print(f"CARESYNC_RELEASE_CONTRACT_OK {command} {identifier}")


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "certify-clone":
            candidate = _configured_database_snapshot(
                expected_revision=TARGET_REVISION,
                require_runtime_certificate=True,
            )
            certificate = create_clone_certificate(
                restore_receipt_path=args.restore_receipt,
                output_path=args.output,
                candidate_snapshot=candidate,
            )
            identifier = certificate["certificateId"]
        elif args.command == "inventory-physical-backup":
            inventory_payload = create_physical_backup_inventory(
                pgdata=args.pgdata,
                output_path=args.output,
            )
            identifier = inventory_payload["sha256Tree"]
        elif args.command == "verify-physical-backup-inventory":
            inventory_payload = verify_physical_backup_inventory(
                pgdata=args.pgdata,
                inventory_path=args.inventory,
            )
            identifier = inventory_payload["sha256Tree"]
        elif args.command == "atomic-rename-no-replace":
            atomic_rename_no_replace(args.source, args.destination)
            identifier = args.destination.name
        elif args.command == "durable-publish-private-file":
            durable_publish_private_file(args.source, args.destination)
            identifier = args.destination.name
        elif args.command == "durable-replace-private-file":
            durable_publish_private_file(
                args.source,
                args.destination,
                replace_existing=True,
            )
            identifier = args.destination.name
        elif args.command == "durable-remove-private-file":
            durable_remove_private_file(args.path)
            identifier = args.path.name
        elif args.command == "durable-rename-private-fence":
            durable_rename_private_fence_no_replace(
                args.source,
                args.destination,
            )
            identifier = args.destination.name
        elif args.command == "ensure-private-directory":
            ensure_private_directory(args.path)
            identifier = args.path.name
        elif args.command == "durability-barrier-private-file":
            durability_barrier_private_file(args.path)
            identifier = args.path.name
        elif args.command == "validate-private-tree":
            validate_private_tree(args.path)
            identifier = args.path.name
        elif args.command == "durability-barrier-private-tree":
            durability_barrier_private_tree(args.path)
            identifier = args.path.name
        elif args.command == "observe-physical-rehearsal":
            source, online_attestation = _configured_physical_rehearsal_inputs()
            observation = create_physical_rehearsal_observation(
                rehearsal_snapshot=source,
                physical_backup_manifest_path=args.physical_backup_manifest,
                physical_backup_inventory_path=args.physical_backup_inventory,
                retained_identity_path=args.retained_identity,
                observation_path=args.observation,
                online_attestation=online_attestation,
            )
            identifier = observation["rehearsalId"]
        elif args.command == "certify-physical-rehearsal":
            receipt = create_physical_rehearsal_receipt(
                observation_path=args.observation,
                physical_backup_manifest_path=args.physical_backup_manifest,
                physical_backup_inventory_path=args.physical_backup_inventory,
                retained_identity_path=args.retained_identity,
                offline_control=collect_offline_rehearsal_control(
                    args.rehearsal_pgdata
                ),
                receipt_path=args.receipt,
            )
            identifier = receipt["rehearsalId"]
        elif args.command == "verify-physical-rehearsal":
            receipt = verify_physical_rehearsal_receipt(
                rehearsal_receipt_path=args.receipt,
                rehearsal_observation_path=args.observation,
                physical_backup_manifest_path=args.physical_backup_manifest,
                physical_backup_inventory_path=args.physical_backup_inventory,
                retained_identity_path=args.retained_identity,
            )
            identifier = receipt["rehearsalId"]
        elif args.command == "prepare":
            source = _configured_database_snapshot(
                expected_revision=SOURCE_REVISION,
                require_runtime_certificate=False,
            )
            receipt = create_candidate_receipt(
                source_snapshot=source,
                clone_certificate_path=args.clone_certificate,
                artifact_paths=_artifact_map(args.artifact),
                release_payload_path=args.release_payload,
                receipt_path=args.receipt,
            )
            identifier = receipt["releaseId"]
        elif args.command == "verify-prepare-receipt":
            receipt = verify_candidate_receipt(
                receipt_path=args.candidate_receipt,
                clone_certificate_path=args.clone_certificate,
                release_payload_path=args.release_payload,
                artifact_paths=_artifact_map(args.artifact),
            )
            identifier = receipt["releaseId"]
        elif args.command == "certify-live":
            promoted = _configured_database_snapshot(
                expected_revision=TARGET_REVISION,
                require_runtime_certificate=True,
            )
            receipt = create_commit_receipt(
                candidate_receipt_path=args.candidate_receipt,
                clone_certificate_path=args.clone_certificate,
                release_payload_path=args.release_payload,
                artifact_paths=_artifact_map(args.artifact),
                promoted_snapshot=promoted,
                receipt_path=args.receipt,
            )
            identifier = receipt["releaseId"]
        elif args.command == "verify-commit-receipt":
            receipt = verify_commit_receipt(
                commit_receipt_path=args.commit_receipt,
                candidate_receipt_path=args.candidate_receipt,
                clone_certificate_path=args.clone_certificate,
                release_payload_path=args.release_payload,
                artifact_paths=_artifact_map(args.artifact),
            )
            identifier = receipt["releaseId"]
        elif args.command == "verify-live-commit":
            current = _configured_database_snapshot(
                expected_revision=TARGET_REVISION,
                require_runtime_certificate=True,
            )
            receipt = verify_live_commit_state(
                current_promoted_snapshot=current,
                commit_receipt_path=args.commit_receipt,
                candidate_receipt_path=args.candidate_receipt,
                clone_certificate_path=args.clone_certificate,
                release_payload_path=args.release_payload,
                artifact_paths=_artifact_map(args.artifact),
            )
            identifier = receipt["releaseId"]
        elif args.command == "finalize-live":
            current = _configured_runtime_state()
            receipt = create_finalization_receipt(
                commit_receipt_path=args.commit_receipt,
                candidate_receipt_path=args.candidate_receipt,
                clone_certificate_path=args.clone_certificate,
                release_payload_path=args.release_payload,
                artifact_paths=_artifact_map(args.artifact),
                current_live_state=current,
                health_evidence=collect_local_health_evidence(),
                receipt_path=args.receipt,
            )
            identifier = receipt["releaseId"]
        elif args.command == "verify-finalization-receipt":
            receipt = verify_finalization_receipt(
                finalization_receipt_path=args.finalization_receipt,
                commit_receipt_path=args.commit_receipt,
                candidate_receipt_path=args.candidate_receipt,
                clone_certificate_path=args.clone_certificate,
                release_payload_path=args.release_payload,
                artifact_paths=_artifact_map(args.artifact),
            )
            identifier = receipt["releaseId"]
        elif args.command == "certify-resume-0039":
            current = _configured_database_snapshot(
                expected_revision=SOURCE_REVISION,
                require_runtime_certificate=False,
            )
            receipt = create_resume_authorization(
                current_source_snapshot=current,
                candidate_receipt_path=args.candidate_receipt,
                clone_certificate_path=args.clone_certificate,
                release_payload_path=args.release_payload,
                artifact_paths=_artifact_map(args.artifact),
                authorization_path=args.authorization,
            )
            identifier = receipt["releaseId"]
        elif args.command == "verify-resume-authorization":
            current = _configured_database_snapshot(
                expected_revision=SOURCE_REVISION,
                require_runtime_certificate=False,
            )
            receipt = verify_resume_authorization(
                authorization_path=args.authorization,
                current_source_snapshot=current,
                candidate_receipt_path=args.candidate_receipt,
                clone_certificate_path=args.clone_certificate,
                release_payload_path=args.release_payload,
                artifact_paths=_artifact_map(args.artifact),
            )
            identifier = receipt["releaseId"]
        else:  # pragma: no cover - argparse enforces this branch.
            raise ReleaseContractError("Unknown release command")
    except ReleaseContractError as error:
        print(f"CareSync release contract failed: {error}", file=sys.stderr)
        return 2
    _success(args.command, identifier)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
