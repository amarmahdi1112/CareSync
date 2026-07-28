"""Encrypted, candidate-owned storage for confidential staff screening originals."""

from __future__ import annotations

import base64
import hashlib
import os
import re
import stat
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import HTTPException, UploadFile, status

from app.basic.family_evidence_vault import (
    PrivateObjectHandle,
    ScannerUnavailable,
    safe_original_filename,
    scan_private_object,
    validate_scanned_document,
)
from app.core.config import Settings

READ_CHUNK_BYTES = 64 * 1024
MAGIC = b"CSHRV1\x00\x00"
NONCE_BYTES = 12
SUPPORTED_MEDIA_SUFFIXES = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
}
LEGACY_PLAINTEXT_NAME = ".screening-upload"
ENCRYPTED_NAME = "v1.enc"
_IDENTIFIER_COMPONENT = re.compile(r"[0-9a-f]{32}")


@dataclass(frozen=True)
class StoredScreeningObject:
    storage_reference: str
    media_type: str
    byte_size: int
    content_sha256: str
    ciphertext_sha256: str
    original_filename: str | None
    encryption_key_id: str
    scanner_engine: str
    scanner_version: str
    scanned_at: datetime


@dataclass(frozen=True)
class StaffScreeningEvidenceRuntimeStatus:
    state: Literal["ready", "unavailable"]

    @property
    def available(self) -> bool:
        return self.state == "ready"


@dataclass(frozen=True)
class _PrivateInodeState:
    device: int
    inode: int
    mode: int
    owner: int
    links: int
    size: int
    modified_ns: int
    changed_ns: int


def _directory_flags() -> int:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    return flags


def _root_fd(settings: Settings, *, create: bool) -> int:
    root = settings.resolved_staff_screening_vault_path
    descriptor = os.open(root.anchor, _directory_flags())
    try:
        components = root.parts[1:]
        for index, component in enumerate(components):
            is_root = index == len(components) - 1
            created = False
            if create and is_root:
                try:
                    os.mkdir(component, mode=0o700, dir_fd=descriptor)
                    os.fsync(descriptor)
                    created = True
                except FileExistsError:
                    pass
            next_descriptor = os.open(component, _directory_flags(), dir_fd=descriptor)
            measured = os.fstat(next_descriptor)
            if not stat.S_ISDIR(measured.st_mode):
                os.close(next_descriptor)
                raise RuntimeError("Staff screening vault component is not a directory")
            if is_root:
                if hasattr(os, "geteuid") and measured.st_uid != os.geteuid():
                    os.close(next_descriptor)
                    raise RuntimeError("Staff screening vault root is not owned by this process")
                if created:
                    os.fchmod(next_descriptor, 0o700)
                    measured = os.fstat(next_descriptor)
                if measured.st_mode & 0o077:
                    os.close(next_descriptor)
                    raise RuntimeError("Staff screening vault root is not private")
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _open_or_create_directory(parent_fd: int, name: str) -> int:
    created = False
    try:
        os.mkdir(name, mode=0o700, dir_fd=parent_fd)
        os.fsync(parent_fd)
        created = True
    except FileExistsError:
        pass
    descriptor = os.open(name, _directory_flags(), dir_fd=parent_fd)
    measured = os.fstat(descriptor)
    if not stat.S_ISDIR(measured.st_mode) or measured.st_mode & 0o077:
        os.close(descriptor)
        raise RuntimeError("Staff screening vault directory is not private")
    if created:
        os.fchmod(descriptor, 0o700)
    return descriptor


def _version_parent(
    settings: Settings,
    *,
    user_id: UUID,
    document_id: UUID,
    version_id: UUID,
    create: bool,
) -> int:
    descriptor = _root_fd(settings, create=create)
    try:
        for name in (user_id.hex, document_id.hex, version_id.hex):
            next_descriptor = (
                _open_or_create_directory(descriptor, name)
                if create
                else os.open(name, _directory_flags(), dir_fd=descriptor)
            )
            measured = os.fstat(next_descriptor)
            if not stat.S_ISDIR(measured.st_mode) or measured.st_mode & 0o077:
                os.close(next_descriptor)
                raise RuntimeError("Staff screening vault directory is not private")
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _private_file_flags(access_mode: int, *, create: bool = False) -> int:
    flags = access_mode
    if create:
        flags |= os.O_CREAT | os.O_EXCL
    if access_mode == os.O_RDONLY and hasattr(os, "O_NONBLOCK"):
        flags |= os.O_NONBLOCK
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    return flags


def _same_inode(first: os.stat_result, second: os.stat_result) -> bool:
    return (first.st_dev, first.st_ino) == (second.st_dev, second.st_ino)


def _validate_private_directory_inode(measured: os.stat_result) -> None:
    if (
        not stat.S_ISDIR(measured.st_mode)
        or (hasattr(os, "geteuid") and measured.st_uid != os.geteuid())
        or stat.S_IMODE(measured.st_mode) != 0o700
    ):
        raise RuntimeError("Staff screening vault contains an unsafe directory")


def _private_inode_state(
    descriptor: int,
    maximum_bytes: int,
    *,
    expected_links: int,
    allow_empty: bool = False,
) -> _PrivateInodeState:
    measured = os.fstat(descriptor)
    if (
        not stat.S_ISREG(measured.st_mode)
        or measured.st_nlink != expected_links
        or (hasattr(os, "geteuid") and measured.st_uid != os.geteuid())
        or stat.S_IMODE(measured.st_mode) != 0o600
        or (not allow_empty and measured.st_size < 1)
        or measured.st_size > maximum_bytes
    ):
        raise RuntimeError("Staff screening temporary object is unsafe")
    return _PrivateInodeState(
        device=measured.st_dev,
        inode=measured.st_ino,
        mode=measured.st_mode,
        owner=measured.st_uid,
        links=measured.st_nlink,
        size=measured.st_size,
        modified_ns=measured.st_mtime_ns,
        changed_ns=measured.st_ctime_ns,
    )


def _unlink_created_entry_if_same(parent_fd: int, name: str, measured: os.stat_result) -> None:
    try:
        current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if _same_inode(current, measured):
            os.unlink(name, dir_fd=parent_fd)
            os.fsync(parent_fd)
    except OSError:
        return


def _new_anonymous_private_object(parent_fd: int) -> PrivateObjectHandle:
    """Create a 0600 inode, unlink it before use, and retain only its fd."""

    for _ in range(32):
        name = f".screening-anonymous-{os.urandom(18).hex()}"
        try:
            descriptor = os.open(
                name,
                _private_file_flags(os.O_RDWR, create=True),
                0o600,
                dir_fd=parent_fd,
            )
        except FileExistsError:
            continue
        measured = os.fstat(descriptor)
        try:
            os.fchmod(descriptor, 0o600)
            measured = os.fstat(descriptor)
            _private_inode_state(
                descriptor,
                0,
                expected_links=1,
                allow_empty=True,
            )
            entry = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            if not _same_inode(measured, entry):
                raise RuntimeError("Staff screening temporary object changed identity")
            os.unlink(name, dir_fd=parent_fd)
            os.fsync(parent_fd)
            _private_inode_state(
                descriptor,
                0,
                expected_links=0,
                allow_empty=True,
            )
            return PrivateObjectHandle(descriptor, "anonymous-screening-upload")
        except BaseException:
            _unlink_created_entry_if_same(parent_fd, name, measured)
            os.close(descriptor)
            raise
    raise RuntimeError("Staff screening temporary object could not be allocated")


def _write_all(descriptor: int, value: bytes) -> None:
    remaining = memoryview(value)
    while remaining:
        written = os.write(descriptor, remaining)
        if written < 1:
            raise OSError("Staff screening temporary object write failed")
        remaining = remaining[written:]


def _read_post_scan_plaintext(
    handle: PrivateObjectHandle,
    maximum_bytes: int,
    expected_state: _PrivateInodeState,
) -> tuple[bytearray, str]:
    if _private_inode_state(handle.descriptor, maximum_bytes, expected_links=0) != expected_state:
        raise RuntimeError("Staff screening temporary object changed during validation")
    handle.rewind()
    plaintext = bytearray()
    digest = hashlib.sha256()
    while True:
        chunk = os.read(
            handle.descriptor,
            min(READ_CHUNK_BYTES, maximum_bytes + 1 - len(plaintext)),
        )
        if not chunk:
            break
        plaintext.extend(chunk)
        digest.update(chunk)
        if len(plaintext) > maximum_bytes:
            raise RuntimeError("Staff screening temporary object exceeded its limit")
    if len(plaintext) != expected_state.size:
        raise RuntimeError("Staff screening temporary object changed size")
    if _private_inode_state(handle.descriptor, maximum_bytes, expected_links=0) != expected_state:
        raise RuntimeError("Staff screening temporary object changed during validation")
    return plaintext, digest.hexdigest()


def _validate_linked_private_file(
    descriptor: int,
    maximum_bytes: int,
    *,
    allow_empty: bool,
) -> os.stat_result:
    measured = os.fstat(descriptor)
    if (
        not stat.S_ISREG(measured.st_mode)
        or measured.st_nlink != 1
        or (hasattr(os, "geteuid") and measured.st_uid != os.geteuid())
        or stat.S_IMODE(measured.st_mode) != 0o600
        or (not allow_empty and measured.st_size < 1)
        or measured.st_size > maximum_bytes
    ):
        raise RuntimeError("Staff screening vault contains an unsafe object")
    return measured


def _scrub_legacy_plaintext_entry(
    parent_fd: int,
    listed: os.stat_result,
    maximum_bytes: int,
) -> None:
    if not stat.S_ISREG(listed.st_mode):
        raise RuntimeError("Legacy staff screening plaintext is not a regular file")
    descriptor = os.open(
        LEGACY_PLAINTEXT_NAME,
        _private_file_flags(os.O_RDONLY),
        dir_fd=parent_fd,
    )
    try:
        measured = _validate_linked_private_file(
            descriptor,
            maximum_bytes,
            allow_empty=True,
        )
        current = os.stat(
            LEGACY_PLAINTEXT_NAME,
            dir_fd=parent_fd,
            follow_symlinks=False,
        )
        if not _same_inode(listed, measured) or not _same_inode(measured, current):
            raise RuntimeError("Legacy staff screening plaintext changed identity")
        os.unlink(LEGACY_PLAINTEXT_NAME, dir_fd=parent_fd)
        os.fsync(parent_fd)
        if os.fstat(descriptor).st_nlink != 0:
            raise RuntimeError("Legacy staff screening plaintext has unsafe links")
    finally:
        os.close(descriptor)


def _scrub_legacy_plaintext_orphans(root_fd: int, maximum_bytes: int) -> None:
    """Traverse the fixed vault shape without following links and remove old plaintext."""

    pending = [(os.dup(root_fd), 0)]
    try:
        while pending:
            parent_fd, depth = pending.pop()
            try:
                for name in os.listdir(parent_fd):
                    listed = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
                    if name == LEGACY_PLAINTEXT_NAME:
                        _scrub_legacy_plaintext_entry(
                            parent_fd,
                            listed,
                            maximum_bytes,
                        )
                        continue
                    if stat.S_ISLNK(listed.st_mode):
                        raise RuntimeError("Staff screening vault contains a symbolic link")
                    if stat.S_ISDIR(listed.st_mode):
                        if depth >= 3 or _IDENTIFIER_COMPONENT.fullmatch(name) is None:
                            raise RuntimeError(
                                "Staff screening vault contains an unexpected directory"
                            )
                        child_fd = os.open(name, _directory_flags(), dir_fd=parent_fd)
                        try:
                            measured = os.fstat(child_fd)
                            _validate_private_directory_inode(measured)
                            if not _same_inode(listed, measured):
                                raise RuntimeError(
                                    "Staff screening vault directory changed identity"
                                )
                        except BaseException:
                            os.close(child_fd)
                            raise
                        pending.append((child_fd, depth + 1))
                        continue
                    if stat.S_ISREG(listed.st_mode):
                        if depth != 3 or name != ENCRYPTED_NAME:
                            raise RuntimeError(
                                "Staff screening vault contains an unexpected object"
                            )
                        descriptor = os.open(
                            name,
                            _private_file_flags(os.O_RDONLY),
                            dir_fd=parent_fd,
                        )
                        try:
                            measured = _validate_linked_private_file(
                                descriptor,
                                maximum_bytes + 1024,
                                allow_empty=False,
                            )
                            if not _same_inode(listed, measured):
                                raise RuntimeError("Staff screening ciphertext changed identity")
                        finally:
                            os.close(descriptor)
                        continue
                    raise RuntimeError("Staff screening vault contains an unsafe entry")
            finally:
                os.close(parent_fd)
    except BaseException:
        for descriptor, _depth in pending:
            os.close(descriptor)
        raise


def _key(settings: Settings) -> bytes:
    encoded = settings.staff_screening_vault_encryption_key.get_secret_value().strip()
    if not encoded:
        raise ScannerUnavailable("staff_screening_vault_key_unavailable")
    try:
        padded = encoded + "=" * (-len(encoded) % 4)
        value = base64.urlsafe_b64decode(padded.encode("ascii"))
    except (ValueError, UnicodeError):
        raise ScannerUnavailable("staff_screening_vault_key_invalid") from None
    if len(value) != 32:
        raise ScannerUnavailable("staff_screening_vault_key_invalid")
    return value


def _key_for_record(settings: Settings, encryption_key_id: str) -> bytes:
    """Resolve only the configured active key until a historical keyring exists."""

    if encryption_key_id != settings.staff_screening_vault_key_id:
        raise ScannerUnavailable("staff_screening_vault_record_key_unavailable")
    return _key(settings)


def staff_screening_evidence_runtime_status(
    settings: Settings,
) -> StaffScreeningEvidenceRuntimeStatus:
    """Boundedly prove that the shared screening vault and scanner are usable.

    This probe never discloses key or scanner diagnostics.  It verifies the
    configured encryption key, the private vault root, and one inert ClamAV
    scan so staff evidence uploads are not advertised when they would
    immediately fail. The returned state is deliberately non-diagnostic.
    """

    root_descriptor = -1
    try:
        root_descriptor = _root_fd(settings, create=True)
        _scrub_legacy_plaintext_orphans(
            root_descriptor,
            settings.staff_screening_document_max_bytes,
        )
        _key(settings)
        probe_bytes = b"CareSync staff evidence readiness probe\n"
        with _new_anonymous_private_object(root_descriptor) as probe:
            _write_all(probe.descriptor, probe_bytes)
            os.fsync(probe.descriptor)
            state = _private_inode_state(
                probe.descriptor,
                len(probe_bytes),
                expected_links=0,
            )
            result = scan_private_object(probe, settings)
            if (
                _private_inode_state(
                    probe.descriptor,
                    len(probe_bytes),
                    expected_links=0,
                )
                != state
            ):
                raise RuntimeError("Staff evidence probe changed during scan")
            return StaffScreeningEvidenceRuntimeStatus(
                state="ready" if result.decision == "clean" else "unavailable"
            )
    except (OSError, RuntimeError):
        return StaffScreeningEvidenceRuntimeStatus(state="unavailable")
    finally:
        if root_descriptor >= 0:
            os.close(root_descriptor)


def transport_evidence_pipeline_runtime_available(settings: Settings) -> bool:
    """Retain the 0032 Boolean compatibility boundary over the shared probe."""

    return staff_screening_evidence_runtime_status(settings).available


def _detect_media(prefix: bytes) -> str:
    if prefix.startswith(b"%PDF-"):
        return "application/pdf"
    if prefix.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if prefix.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail={"code": "unsupported_screening_document_media"},
    )


def _aad(
    *, user_id: UUID, document_id: UUID, version_id: UUID, media_type: str, key_id: str
) -> bytes:
    return (
        f"caresync-screening-v1:{user_id}:{document_id}:{version_id}:{media_type}:{key_id}"
    ).encode()


async def store_encrypted_screening_upload(
    upload: UploadFile,
    *,
    settings: Settings,
    user_id: UUID,
    document_id: UUID,
    version_id: UUID,
) -> StoredScreeningObject:
    """Validate and scan plaintext, then persist only authenticated ciphertext."""

    key = _key(settings)
    parent_fd = _version_parent(
        settings,
        user_id=user_id,
        document_id=document_id,
        version_id=version_id,
        create=True,
    )
    total = 0
    prefix = bytearray()
    upload_digest = hashlib.sha256()
    plaintext = bytearray()
    handle: PrivateObjectHandle | None = None
    encrypted_created = False
    try:
        handle = _new_anonymous_private_object(parent_fd)
        while True:
            chunk = await upload.read(READ_CHUNK_BYTES)
            if not chunk:
                break
            total += len(chunk)
            if total > settings.staff_screening_document_max_bytes:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail={"code": "screening_document_too_large"},
                )
            if len(prefix) < 16:
                prefix.extend(chunk[: 16 - len(prefix)])
            upload_digest.update(chunk)
            _write_all(handle.descriptor, chunk)
        os.fsync(handle.descriptor)
        if total == 0:
            raise HTTPException(422, detail={"code": "empty_screening_document"})
        media_type = _detect_media(bytes(prefix))
        advisory_type = (upload.content_type or "").split(";", 1)[0].strip().lower()
        if advisory_type not in {"", "application/octet-stream", media_type}:
            raise HTTPException(422, detail={"code": "screening_document_media_mismatch"})

        validated_state = _private_inode_state(
            handle.descriptor,
            settings.staff_screening_document_max_bytes,
            expected_links=0,
        )
        if validated_state.size != total:
            raise RuntimeError("Staff screening temporary object changed size")
        scan_result = scan_private_object(handle, settings)
        if (
            _private_inode_state(
                handle.descriptor,
                settings.staff_screening_document_max_bytes,
                expected_links=0,
            )
            != validated_state
        ):
            raise RuntimeError("Staff screening temporary object changed during scan")
        if scan_result.decision != "clean":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"code": "screening_document_security_scan_rejected"},
            )
        validate_scanned_document(handle, media_type, settings)
        if (
            _private_inode_state(
                handle.descriptor,
                settings.staff_screening_document_max_bytes,
                expected_links=0,
            )
            != validated_state
        ):
            raise RuntimeError("Staff screening temporary object changed during parsing")

        plaintext, content_sha256 = _read_post_scan_plaintext(
            handle,
            settings.staff_screening_document_max_bytes,
            validated_state,
        )
        if content_sha256 != upload_digest.hexdigest():
            raise RuntimeError("Staff screening temporary object content changed")

        nonce = os.urandom(NONCE_BYTES)
        key_id = settings.staff_screening_vault_key_id
        encrypted = (
            MAGIC
            + nonce
            + AESGCM(key).encrypt(
                nonce,
                bytes(plaintext),
                _aad(
                    user_id=user_id,
                    document_id=document_id,
                    version_id=version_id,
                    media_type=media_type,
                    key_id=key_id,
                ),
            )
        )
        encrypted_descriptor = os.open(
            ENCRYPTED_NAME,
            _private_file_flags(os.O_WRONLY, create=True),
            0o600,
            dir_fd=parent_fd,
        )
        encrypted_created = True
        try:
            os.fchmod(encrypted_descriptor, 0o600)
            with os.fdopen(encrypted_descriptor, "wb", closefd=False) as destination:
                destination.write(encrypted)
                destination.flush()
                os.fsync(destination.fileno())
                measured = _validate_linked_private_file(
                    destination.fileno(),
                    len(encrypted),
                    allow_empty=False,
                )
                if measured.st_size != len(encrypted):
                    raise RuntimeError("Staff screening ciphertext write was incomplete")
        finally:
            os.close(encrypted_descriptor)
        os.fsync(parent_fd)
        return StoredScreeningObject(
            storage_reference="/".join(
                (user_id.hex, document_id.hex, version_id.hex, ENCRYPTED_NAME)
            ),
            media_type=media_type,
            byte_size=total,
            content_sha256=content_sha256,
            ciphertext_sha256=hashlib.sha256(encrypted).hexdigest(),
            original_filename=safe_original_filename(upload.filename),
            encryption_key_id=key_id,
            scanner_engine=scan_result.scanner_engine,
            scanner_version=scan_result.scanner_version,
            scanned_at=datetime.now(UTC),
        )
    except BaseException:
        if encrypted_created:
            with suppress(FileNotFoundError):
                os.unlink(ENCRYPTED_NAME, dir_fd=parent_fd)
            with suppress(OSError):
                os.fsync(parent_fd)
        raise
    finally:
        prefix.clear()
        plaintext.clear()
        if handle is not None:
            handle.close()
        os.close(parent_fd)


def _reference_ids(storage_reference: str) -> tuple[UUID, UUID, UUID]:
    match = re.fullmatch(
        r"([0-9a-f]{32})/([0-9a-f]{32})/([0-9a-f]{32})/v1\.enc",
        storage_reference,
    )
    if match is None:
        raise RuntimeError("Staff screening storage reference is invalid")
    return UUID(hex=match.group(1)), UUID(hex=match.group(2)), UUID(hex=match.group(3))


def read_encrypted_screening_object(
    *,
    settings: Settings,
    storage_reference: str,
    media_type: str,
    encryption_key_id: str,
    expected_ciphertext_sha256: str,
    expected_content_sha256: str,
    expected_byte_size: int,
    maximum_bytes: int,
) -> bytes:
    user_id, document_id, version_id = _reference_ids(storage_reference)
    parent_fd = _version_parent(
        settings,
        user_id=user_id,
        document_id=document_id,
        version_id=version_id,
        create=False,
    )
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open("v1.enc", flags, dir_fd=parent_fd)
        try:
            measured = os.fstat(descriptor)
            if (
                not stat.S_ISREG(measured.st_mode)
                or measured.st_mode & 0o077
                or measured.st_size > maximum_bytes + 1024
            ):
                raise RuntimeError("Staff screening ciphertext object is unsafe")
            with os.fdopen(os.dup(descriptor), "rb", closefd=True) as source:
                encrypted = source.read(measured.st_size + 1)
        finally:
            os.close(descriptor)
    finally:
        os.close(parent_fd)
    if hashlib.sha256(encrypted).hexdigest() != expected_ciphertext_sha256:
        raise RuntimeError("Staff screening ciphertext integrity mismatch")
    if not encrypted.startswith(MAGIC) or len(encrypted) <= len(MAGIC) + NONCE_BYTES + 16:
        raise RuntimeError("Staff screening ciphertext envelope is invalid")
    nonce = encrypted[len(MAGIC) : len(MAGIC) + NONCE_BYTES]
    ciphertext = encrypted[len(MAGIC) + NONCE_BYTES :]
    try:
        plaintext = AESGCM(_key_for_record(settings, encryption_key_id)).decrypt(
            nonce,
            ciphertext,
            _aad(
                user_id=user_id,
                document_id=document_id,
                version_id=version_id,
                media_type=media_type,
                key_id=encryption_key_id,
            ),
        )
    except InvalidTag:
        raise RuntimeError("Staff screening ciphertext authentication failed") from None
    if len(plaintext) != expected_byte_size or len(plaintext) > maximum_bytes:
        raise RuntimeError("Staff screening plaintext size did not match its record")
    if hashlib.sha256(plaintext).hexdigest() != expected_content_sha256:
        raise RuntimeError("Staff screening plaintext digest did not match its record")
    return plaintext


def delete_screening_object(settings: Settings, storage_reference: str) -> None:
    try:
        user_id, document_id, version_id = _reference_ids(storage_reference)
        parent_fd = _version_parent(
            settings,
            user_id=user_id,
            document_id=document_id,
            version_id=version_id,
            create=False,
        )
        try:
            os.unlink("v1.enc", dir_fd=parent_fd)
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    except (FileNotFoundError, OSError, RuntimeError):
        return
