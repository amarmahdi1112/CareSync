"""Private, server-measured storage and malware scanning for family evidence.

The browser supplies bytes and an advisory filename only. CareSync owns the
object identifier, private key, media detection, size, digest and scan result.
No path from this module is mounted by the Basic application.
"""

from __future__ import annotations

import hashlib
import math
import os
import re
import shutil
import stat
import subprocess
import sys
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException, UploadFile, status

from app.core.config import Settings

READ_CHUNK_BYTES = 64 * 1024
DOCUMENT_EVIDENCE_KINDS = frozenset(
    {
        "identity_document",
        "custody_document",
        "court_order",
        "signed_consent",
        "signed_release_delegation",
        "other_document",
    }
)
NON_DOCUMENT_EVIDENCE_KINDS = frozenset({"guardian_attestation", "staff_witness"})
SUPPORTED_MEDIA_SUFFIXES = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
}


class ScannerUnavailable(RuntimeError):
    """Raised when no configured scanner can produce an authoritative result."""


@dataclass(frozen=True)
class StoredEvidenceObject:
    storage_reference: str
    media_type: str
    byte_size: int
    content_sha256: str
    original_filename: str | None


@dataclass(frozen=True)
class MalwareScanResult:
    decision: str
    scanner_engine: str
    scanner_version: str
    scanner_signature: str | None
    reason_code: str | None


@dataclass
class PrivateObjectHandle:
    """A no-follow, inode-pinned private evidence object."""

    descriptor: int
    storage_reference: str

    def __enter__(self) -> PrivateObjectHandle:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        if self.descriptor >= 0:
            os.close(self.descriptor)
            self.descriptor = -1

    def rewind(self) -> None:
        os.lseek(self.descriptor, 0, os.SEEK_SET)

    def validate_private_inode(self, maximum: int) -> os.stat_result:
        measured = os.fstat(self.descriptor)
        if (
            not stat.S_ISREG(measured.st_mode)
            or measured.st_nlink != 1
            or (hasattr(os, "geteuid") and measured.st_uid != os.geteuid())
            or measured.st_mode & 0o077
            or measured.st_size < 1
            or measured.st_size > maximum
        ):
            raise RuntimeError("Evidence object is not a private regular inode")
        return measured

    @property
    def subprocess_path(self) -> str:
        prefix = "/proc/self/fd" if Path("/proc/self/fd").is_dir() else "/dev/fd"
        return f"{prefix}/{self.descriptor}"


def safe_original_filename(value: str | None) -> str | None:
    if not value:
        return None
    basename = value.replace("\\", "/").split("/")[-1]
    # Display-only metadata still gets an ASCII allowlist so control, bidi,
    # separator and confusable characters cannot leak into later UI/header use.
    cleaned = re.sub(r"[^A-Za-z0-9 ._()\-]+", "_", basename)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned[:255] or None


def _directory_open_flags() -> int:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    return flags


def _open_vault_root_fd(settings: Settings, *, create: bool) -> int:
    """Traverse the lexical root one component at a time without symlinks."""

    root = settings.resolved_family_evidence_vault_path
    if not root.is_absolute():
        raise RuntimeError("Family evidence vault root must be absolute")
    descriptor = os.open(root.anchor, _directory_open_flags())
    try:
        for component in root.parts[1:]:
            created = False
            if create:
                try:
                    os.mkdir(component, mode=0o700, dir_fd=descriptor)
                    created = True
                except FileExistsError:
                    pass
            next_descriptor = os.open(
                component, _directory_open_flags(), dir_fd=descriptor
            )
            if created:
                os.fchmod(next_descriptor, 0o700)
                os.fsync(descriptor)
            os.close(descriptor)
            descriptor = next_descriptor
        if create:
            os.fchmod(descriptor, 0o700)
        if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise RuntimeError("Family evidence vault root is not a directory")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _vault_root(settings: Settings) -> Path:
    root = settings.resolved_family_evidence_vault_path
    try:
        descriptor = _open_vault_root_fd(settings, create=True)
    except OSError as error:
        raise RuntimeError(
            "Family evidence vault contains an unsafe path component"
        ) from error
    os.close(descriptor)
    return root


def _open_or_create_directory(parent_fd: int, name: str) -> int:
    with suppress(FileExistsError):
        os.mkdir(name, mode=0o700, dir_fd=parent_fd)
    descriptor = os.open(name, _directory_open_flags(), dir_fd=parent_fd)
    os.fchmod(descriptor, 0o700)
    measured = os.fstat(descriptor)
    if not stat.S_ISDIR(measured.st_mode) or measured.st_mode & 0o077:
        os.close(descriptor)
        raise RuntimeError("Family evidence vault directory is not private")
    return descriptor


def _new_private_parent(
    settings: Settings,
    organization_id: UUID,
    family_id: UUID,
    object_id: UUID,
) -> tuple[Path, int]:
    root = _vault_root(settings)
    root_fd = _open_vault_root_fd(settings, create=False)
    organization_fd = family_fd = -1
    try:
        organization_fd = _open_or_create_directory(root_fd, organization_id.hex)
        family_fd = _open_or_create_directory(organization_fd, family_id.hex)
        try:
            os.mkdir(object_id.hex, mode=0o700, dir_fd=family_fd)
        except FileExistsError:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "evidence_object_storage_collision"},
            ) from None
        parent_fd = os.open(object_id.hex, _directory_open_flags(), dir_fd=family_fd)
        os.fchmod(parent_fd, 0o700)
        os.fsync(family_fd)
        family_path = root / organization_id.hex / family_id.hex
        return family_path / object_id.hex, parent_fd
    finally:
        if family_fd >= 0:
            os.close(family_fd)
        if organization_fd >= 0:
            os.close(organization_fd)
        os.close(root_fd)


def _validated_reference_parts(storage_reference: str) -> tuple[str, str, str, str]:
    match = re.fullmatch(
        r"([0-9a-f]{32})/([0-9a-f]{32})/([0-9a-f]{32})/"
        r"(v1\.(?:pdf|png|jpg))",
        storage_reference,
    )
    if match is None:
        raise RuntimeError("Evidence object storage reference is invalid")
    return match.group(1), match.group(2), match.group(3), match.group(4)


def _open_private_parent(
    settings: Settings, storage_reference: str
) -> tuple[int, str]:
    organization, family, object_id, filename = _validated_reference_parts(
        storage_reference
    )
    descriptor = _open_vault_root_fd(settings, create=False)
    try:
        for component in (organization, family, object_id):
            next_descriptor = os.open(
                component, _directory_open_flags(), dir_fd=descriptor
            )
            measured = os.fstat(next_descriptor)
            if not stat.S_ISDIR(measured.st_mode) or measured.st_mode & 0o077:
                os.close(next_descriptor)
                raise RuntimeError("Evidence object directory is not private")
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor, filename
    except BaseException:
        os.close(descriptor)
        raise


def open_private_object(
    settings: Settings, storage_reference: str
) -> PrivateObjectHandle:
    parent_fd, filename = _open_private_parent(settings, storage_reference)
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    descriptor = -1
    try:
        descriptor = os.open(filename, flags, dir_fd=parent_fd)
        handle = PrivateObjectHandle(descriptor, storage_reference)
        handle.validate_private_inode(settings.family_evidence_max_bytes)
        return handle
    except BaseException:
        if descriptor >= 0:
            os.close(descriptor)
        raise
    finally:
        os.close(parent_fd)


def _detect_media(prefix: bytes) -> str:
    if prefix.startswith(b"%PDF-"):
        return "application/pdf"
    if prefix.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if prefix.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail={"code": "unsupported_evidence_media"},
    )


def _subprocess_source(
    source: Path | PrivateObjectHandle,
) -> tuple[str, tuple[int, ...]]:
    if isinstance(source, PrivateObjectHandle):
        source.rewind()
        return source.subprocess_path, (source.descriptor,)
    return os.fspath(source), ()


def validate_scanned_document(
    source: Path | PrivateObjectHandle, media_type: str, settings: Settings
) -> None:
    """Parse in an isolated, resource-bounded subprocess after malware scan."""

    worker = Path(__file__).with_name("family_evidence_parser_worker.py")
    source_path, pass_fds = _subprocess_source(source)
    argv = [
        sys.executable,
        "-I",
        "-B",
        os.fspath(worker),
        source_path,
        media_type,
        str(settings.family_evidence_max_image_pixels),
        str(settings.family_evidence_max_pdf_pages),
        str(max(1, min(30, math.ceil(settings.family_evidence_parser_timeout_seconds)))),
        str(1024 * 1024 * 1024),
    ]
    try:
        run_options = {
            "check": False,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.DEVNULL,
            "text": True,
            "timeout": settings.family_evidence_parser_timeout_seconds,
            "close_fds": True,
            "start_new_session": True,
        }
        if pass_fds:
            run_options["pass_fds"] = pass_fds
        completed = subprocess.run(argv, **run_options)
    except (OSError, subprocess.SubprocessError):
        raise HTTPException(
            status_code=422, detail={"code": "invalid_evidence_document"}
        ) from None
    if isinstance(source, PrivateObjectHandle):
        source.rewind()
    if completed.returncode == 0:
        return
    code = _bounded_output(completed.stdout or "invalid_evidence_document", 80)
    allowed_codes = {
        "active_evidence_pdf",
        "animated_evidence_image",
        "encrypted_evidence_pdf",
        "evidence_image_pixel_limit",
        "evidence_media_mismatch",
        "evidence_pdf_page_limit",
        "invalid_evidence_document",
        "pdf_structure_limit",
        "unsupported_evidence_media",
    }
    raise HTTPException(
        status_code=(413 if code == "evidence_image_pixel_limit" else 422),
        detail={"code": code if code in allowed_codes else "invalid_evidence_document"},
    )


async def store_private_upload(
    upload: UploadFile,
    *,
    settings: Settings,
    organization_id: UUID,
    family_id: UUID,
    object_id: UUID,
) -> StoredEvidenceObject:
    """Stream one bounded upload into a server-generated private object key."""

    parent, parent_fd = _new_private_parent(
        settings, organization_id, family_id, object_id
    )
    temporary_name = ".v1.uploading"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(temporary_name, flags, 0o600, dir_fd=parent_fd)
    digest = hashlib.sha256()
    total = 0
    prefix = bytearray()
    final_name: str | None = None
    final_published = False
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as destination:
            os.fchmod(destination.fileno(), 0o600)
            while True:
                chunk = await upload.read(READ_CHUNK_BYTES)
                if not chunk:
                    break
                total += len(chunk)
                if total > settings.family_evidence_max_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail={"code": "evidence_file_too_large"},
                    )
                if len(prefix) < 16:
                    prefix.extend(chunk[: 16 - len(prefix)])
                digest.update(chunk)
                destination.write(chunk)
            destination.flush()
            os.fsync(destination.fileno())
        if total == 0:
            raise HTTPException(status_code=422, detail={"code": "empty_evidence_file"})
        media_type = _detect_media(bytes(prefix))
        advisory_type = (upload.content_type or "").split(";", 1)[0].strip().lower()
        if advisory_type not in {"", "application/octet-stream", media_type}:
            raise HTTPException(
                status_code=422,
                detail={"code": "evidence_media_mismatch"},
            )
        suffix = SUPPORTED_MEDIA_SUFFIXES[media_type]
        final_name = f"v1{suffix}"
        try:
            # link(2) publishes without replacement; a colliding orphan can
            # never have its bytes silently overwritten.
            os.link(
                temporary_name,
                final_name,
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
                follow_symlinks=False,
            )
            final_published = True
        except FileExistsError:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "evidence_object_storage_collision"},
            ) from None
        os.unlink(temporary_name, dir_fd=parent_fd)
        os.fsync(parent_fd)
        reference = "/".join(
            (organization_id.hex, family_id.hex, object_id.hex, final_name)
        )
        return StoredEvidenceObject(
            storage_reference=reference,
            media_type=media_type,
            byte_size=total,
            content_sha256=digest.hexdigest(),
            original_filename=safe_original_filename(upload.filename),
        )
    except BaseException:
        with suppress(FileNotFoundError):
            os.unlink(temporary_name, dir_fd=parent_fd)
        if final_published and final_name is not None:
            try:
                os.unlink(final_name, dir_fd=parent_fd)
                os.fsync(parent_fd)
            except OSError:
                # A private orphan is safer than hiding the original failure;
                # offline reconciliation can remove it before any DB adoption.
                pass
        raise
    finally:
        os.close(parent_fd)


def delete_private_object(settings: Settings, storage_reference: str) -> None:
    parent_fd = -1
    try:
        parent_fd, filename = _open_private_parent(settings, storage_reference)
        os.unlink(filename, dir_fd=parent_fd)
        os.fsync(parent_fd)
    except (FileNotFoundError, OSError, RuntimeError):
        return
    finally:
        if parent_fd >= 0:
            os.close(parent_fd)


def _scanner_binary(settings: Settings) -> Path:
    configured = settings.family_evidence_scanner_path
    if configured is not None:
        candidate = configured.expanduser().resolve()
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
        raise ScannerUnavailable("configured_scanner_unavailable")
    # Prefer the local scanner because CareSync can enforce its per-process
    # resource-limit verdict.  clamdscan delegates that policy to a daemon and
    # cannot prove the daemon has AlertExceedsMax enabled.
    discovered = shutil.which("clamscan") or shutil.which("clamdscan")
    if not discovered:
        raise ScannerUnavailable("malware_scanner_unavailable")
    return Path(discovered).resolve()


def _bounded_output(value: str, maximum: int = 300) -> str:
    return " ".join(value.split())[:maximum]


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _validated_scanner_version(output: str, settings: Settings) -> str:
    bounded = _bounded_output(output, 160)
    match = re.search(
        r"\bClamAV\s+([A-Za-z0-9][A-Za-z0-9._+-]{0,79})/([1-9][0-9]*)/"
        r"([A-Z][a-z]{2}\s+[A-Z][a-z]{2}\s+[0-9]{1,2}\s+"
        r"[0-9]{2}:[0-9]{2}:[0-9]{2}\s+[0-9]{4})\b",
        bounded,
    )
    if match is None:
        raise ScannerUnavailable("malware_scanner_definitions_unverified")
    try:
        definition_time = datetime.strptime(
            match.group(3), "%a %b %d %H:%M:%S %Y"
        ).replace(tzinfo=UTC)
    except ValueError as error:
        raise ScannerUnavailable("malware_scanner_definitions_unverified") from error
    now = _now_utc()
    if definition_time > now + timedelta(hours=24) or (
        now - definition_time
        > timedelta(hours=settings.family_evidence_scanner_max_definition_age_hours)
    ):
        raise ScannerUnavailable("malware_scanner_definitions_stale")
    # Persist only the parsed identity.  Scanner stdout is not receipt data:
    # warnings, paths or terminal text appended to a valid version must never
    # cross the redaction boundary.
    return f"ClamAV {match.group(1)}/{match.group(2)}/{match.group(3)}"


def scan_private_object(
    source: Path | PrivateObjectHandle, settings: Settings
) -> MalwareScanResult:
    """Run ClamAV without a shell and translate only its documented exit codes."""

    binary = _scanner_binary(settings)
    engine = binary.name
    if engine == "clamdscan":
        # clamdscan has no per-invocation equivalent of clamscan's
        # --alert-exceeds-max.  Without a separately attested clamd contract,
        # daemon scan-limit exhaustion may be reported as clean.
        raise ScannerUnavailable("malware_scanner_limit_policy_unverified")
    try:
        version_run = subprocess.run(
            [str(binary), "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=min(settings.family_evidence_scanner_timeout_seconds, 15.0),
        )
        version_output = version_run.stdout or version_run.stderr
        if version_run.returncode != 0 or not version_output.strip():
            raise ScannerUnavailable("malware_scanner_failed")
        version = _validated_scanner_version(version_output, settings)
        scan_argv = [
            str(binary),
            "--no-summary",
            "--alert-exceeds-max=yes",
        ]
        scan_options = {
            "check": False,
            "capture_output": True,
            "text": True,
            "timeout": settings.family_evidence_scanner_timeout_seconds,
        }
        if isinstance(source, PrivateObjectHandle) and engine == "clamscan":
            # macOS denies a child process reopening an inherited descriptor
            # through /dev/fd. Feed the already pinned inode to clamscan's
            # documented stdin target instead; no pathname is reopened.
            source.rewind()
            scan_argv.append("-")
            scan_options["stdin"] = source.descriptor
        else:
            source_path, pass_fds = _subprocess_source(source)
            scan_argv.append(source_path)
            if pass_fds:
                scan_options["pass_fds"] = pass_fds
        completed = subprocess.run(scan_argv, **scan_options)
    except (OSError, subprocess.SubprocessError, UnicodeError, ValueError) as error:
        raise ScannerUnavailable("malware_scanner_failed") from error
    if isinstance(source, PrivateObjectHandle):
        source.rewind()
    output = _bounded_output("\n".join((completed.stdout, completed.stderr)))
    if completed.returncode == 0:
        return MalwareScanResult(
            decision="clean",
            scanner_engine=engine,
            scanner_version=version,
            scanner_signature=None,
            reason_code=None,
        )
    if completed.returncode == 1:
        signature = None
        if " FOUND" in output and ":" in output:
            signature = output.rsplit(":", 1)[-1].removesuffix(" FOUND").strip()[:160] or None
        return MalwareScanResult(
            decision="rejected",
            scanner_engine=engine,
            scanner_version=version,
            scanner_signature=signature,
            reason_code="malware_detected",
        )
    raise ScannerUnavailable("malware_scanner_failed")


def read_private_object(source: Path | PrivateObjectHandle, maximum: int) -> bytes:
    if isinstance(source, PrivateObjectHandle):
        source.validate_private_inode(maximum)
        source.rewind()
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(source.descriptor, min(READ_CHUNK_BYTES, maximum + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            chunks.append(chunk)
            if total > maximum:
                break
        source.rewind()
        data = b"".join(chunks)
    else:
        data = source.read_bytes()
    if not data or len(data) > maximum:
        raise RuntimeError("Evidence object no longer matches its bounded storage contract")
    return data


def stream_private_object(handle: PrivateObjectHandle):
    """Yield the already-verified inode and close it when the response ends."""

    try:
        handle.rewind()
        while True:
            chunk = os.read(handle.descriptor, READ_CHUNK_BYTES)
            if not chunk:
                break
            yield chunk
    finally:
        handle.close()


def detect_bytes_media(data: bytes) -> str:
    """Small test helper that applies the same server-owned magic detector."""

    return _detect_media(data[:16])
