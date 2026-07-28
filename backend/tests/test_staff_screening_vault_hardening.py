"""Regression proofs for the anonymous staff-screening upload boundary."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import os
import stat
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import HTTPException, UploadFile

from app.basic import staff_screening_vault as vault
from app.basic.family_evidence_vault import PrivateObjectHandle
from app.core.config import Settings

USER_ID = UUID(int=1)
DOCUMENT_ID = UUID(int=2)
VERSION_ID = UUID(int=3)
PDF_BYTES = b"%PDF-1.4\nprivate-screening-document\n%%EOF\n"


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        database_path=tmp_path / "caresync.db",
        database_read_only=False,
        staff_screening_vault_path=tmp_path / "screening-vault",
        staff_screening_vault_encryption_key=base64.urlsafe_b64encode(b"k" * 32).decode(),
    )


def _clean_result():
    return SimpleNamespace(
        decision="clean",
        scanner_engine="test-scanner",
        scanner_version="test-scanner-1",
    )


def _read_handle(handle: PrivateObjectHandle) -> bytes:
    measured = os.fstat(handle.descriptor)
    offset = os.lseek(handle.descriptor, 0, os.SEEK_CUR)
    try:
        os.lseek(handle.descriptor, 0, os.SEEK_SET)
        return os.read(handle.descriptor, measured.st_size + 1)
    finally:
        os.lseek(handle.descriptor, offset, os.SEEK_SET)


def _upload(settings: Settings) -> vault.StoredScreeningObject:
    return asyncio.run(
        vault.store_encrypted_screening_upload(
            UploadFile(BytesIO(PDF_BYTES), filename="screening.pdf"),
            settings=settings,
            user_id=USER_ID,
            document_id=DOCUMENT_ID,
            version_id=VERSION_ID,
        )
    )


def _version_path(settings: Settings) -> Path:
    return (
        settings.resolved_staff_screening_vault_path
        / USER_ID.hex
        / DOCUMENT_ID.hex
        / VERSION_ID.hex
    )


def _make_private_version_path(settings: Settings) -> Path:
    current = settings.resolved_staff_screening_vault_path
    current.mkdir(mode=0o700)
    current.chmod(0o700)
    for component in (USER_ID.hex, DOCUMENT_ID.hex, VERSION_ID.hex):
        current /= component
        current.mkdir(mode=0o700)
        current.chmod(0o700)
    return current


def _vault_files(settings: Settings) -> list[Path]:
    return [
        path for path in settings.resolved_staff_screening_vault_path.rglob("*") if path.is_file()
    ]


def test_scan_parse_and_encryption_use_one_anonymous_inode_and_identical_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path)
    seen: dict[str, object] = {}

    def clean_scan(source, _settings):
        assert isinstance(source, PrivateObjectHandle)
        measured = os.fstat(source.descriptor)
        assert stat.S_ISREG(measured.st_mode)
        assert stat.S_IMODE(measured.st_mode) == 0o600
        assert measured.st_nlink == 0
        assert not _vault_files(settings)
        seen["handle"] = source
        seen["inode"] = (measured.st_dev, measured.st_ino)
        seen["scan_bytes"] = _read_handle(source)
        return _clean_result()

    def validate(source, media_type, _settings):
        assert source is seen["handle"]
        measured = os.fstat(source.descriptor)
        assert (measured.st_dev, measured.st_ino) == seen["inode"]
        assert media_type == "application/pdf"
        seen["parse_bytes"] = _read_handle(source)

    class RecordingAESGCM:
        def __init__(self, key: bytes) -> None:
            assert key == b"k" * 32

        def encrypt(self, nonce: bytes, plaintext: bytes, aad: bytes) -> bytes:
            assert len(nonce) == vault.NONCE_BYTES
            assert aad.startswith(b"caresync-screening-v1:")
            seen["encrypted_bytes"] = bytes(plaintext)
            return b"authenticated-ciphertext" + bytes(plaintext)

    monkeypatch.setattr(vault, "scan_private_object", clean_scan)
    monkeypatch.setattr(vault, "validate_scanned_document", validate)
    monkeypatch.setattr(vault, "AESGCM", RecordingAESGCM)

    stored = _upload(settings)

    assert seen["scan_bytes"] == seen["parse_bytes"] == seen["encrypted_bytes"] == PDF_BYTES
    assert stored.content_sha256 == hashlib.sha256(PDF_BYTES).hexdigest()
    assert stored.byte_size == len(PDF_BYTES)
    assert [path.name for path in _version_path(settings).iterdir()] == [vault.ENCRYPTED_NAME]
    assert not list(settings.resolved_staff_screening_vault_path.rglob(".screening-upload"))


def test_authenticated_ciphertext_round_trip_preserves_upload_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path)
    monkeypatch.setattr(vault, "scan_private_object", lambda _source, _settings: _clean_result())
    monkeypatch.setattr(
        vault,
        "validate_scanned_document",
        lambda _source, _media_type, _settings: None,
    )

    stored = _upload(settings)

    assert (
        vault.read_encrypted_screening_object(
            settings=settings,
            storage_reference=stored.storage_reference,
            media_type=stored.media_type,
            encryption_key_id=stored.encryption_key_id,
            expected_ciphertext_sha256=stored.ciphertext_sha256,
            expected_content_sha256=stored.content_sha256,
            expected_byte_size=stored.byte_size,
            maximum_bytes=settings.staff_screening_document_max_bytes,
        )
        == PDF_BYTES
    )


def test_read_refuses_an_unconfigured_record_key_id_even_when_material_is_reused(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path)
    monkeypatch.setattr(vault, "scan_private_object", lambda _source, _settings: _clean_result())
    monkeypatch.setattr(
        vault,
        "validate_scanned_document",
        lambda _source, _media_type, _settings: None,
    )
    stored = _upload(settings)
    rotated_label_only = settings.model_copy(update={"staff_screening_vault_key_id": "local-v2"})

    with pytest.raises(
        vault.ScannerUnavailable,
        match="staff_screening_vault_record_key_unavailable",
    ):
        vault.read_encrypted_screening_object(
            settings=rotated_label_only,
            storage_reference=stored.storage_reference,
            media_type=stored.media_type,
            encryption_key_id=stored.encryption_key_id,
            expected_ciphertext_sha256=stored.ciphertext_sha256,
            expected_content_sha256=stored.content_sha256,
            expected_byte_size=stored.byte_size,
            maximum_bytes=settings.staff_screening_document_max_bytes,
        )


@pytest.mark.parametrize("mutation_phase", ["scan", "parse"])
def test_scanner_or_parser_mutation_fails_closed_before_encryption(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation_phase: str,
) -> None:
    settings = _settings(tmp_path)

    def mutate(source: PrivateObjectHandle) -> None:
        os.lseek(source.descriptor, 0, os.SEEK_END)
        os.write(source.descriptor, b"mutation")
        os.fsync(source.descriptor)

    def scan(source, _settings):
        if mutation_phase == "scan":
            mutate(source)
        return _clean_result()

    def validate(source, _media_type, _settings):
        if mutation_phase == "parse":
            mutate(source)

    monkeypatch.setattr(vault, "scan_private_object", scan)
    monkeypatch.setattr(vault, "validate_scanned_document", validate)

    with pytest.raises(RuntimeError, match="changed during"):
        _upload(settings)

    assert not _vault_files(settings)
    assert not list(settings.resolved_staff_screening_vault_path.rglob(".screening-upload"))


@pytest.mark.parametrize("failure_phase", ["scan", "parse", "encrypt"])
def test_pipeline_failures_leave_no_plaintext_or_ciphertext(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_phase: str,
) -> None:
    settings = _settings(tmp_path)

    def scan(_source, _settings):
        if failure_phase == "scan":
            raise RuntimeError("scanner failed")
        return _clean_result()

    def validate(_source, _media_type, _settings):
        if failure_phase == "parse":
            raise HTTPException(422, detail={"code": "invalid_evidence_document"})

    class FailingAESGCM:
        def __init__(self, _key: bytes) -> None:
            pass

        def encrypt(self, _nonce: bytes, _plaintext: bytes, _aad: bytes) -> bytes:
            if failure_phase == "encrypt":
                raise RuntimeError("encryption failed")
            return b"unused"

    monkeypatch.setattr(vault, "scan_private_object", scan)
    monkeypatch.setattr(vault, "validate_scanned_document", validate)
    monkeypatch.setattr(vault, "AESGCM", FailingAESGCM)

    with pytest.raises((HTTPException, RuntimeError)):
        _upload(settings)

    assert not _vault_files(settings)
    assert not list(settings.resolved_staff_screening_vault_path.rglob(".screening-upload"))


def test_ciphertext_persistence_failure_unlinks_partial_object(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path)
    monkeypatch.setattr(vault, "scan_private_object", lambda _source, _settings: _clean_result())
    monkeypatch.setattr(
        vault,
        "validate_scanned_document",
        lambda _source, _media_type, _settings: None,
    )
    monkeypatch.setattr(
        vault,
        "_validate_linked_private_file",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("ciphertext fsync failed")),
    )

    with pytest.raises(OSError, match="ciphertext fsync failed"):
        _upload(settings)

    assert not _vault_files(settings)


def test_existing_ciphertext_is_never_replaced_or_removed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path)
    version_path = _make_private_version_path(settings)
    ciphertext = version_path / vault.ENCRYPTED_NAME
    ciphertext.write_bytes(b"existing-ciphertext")
    ciphertext.chmod(0o600)
    monkeypatch.setattr(vault, "scan_private_object", lambda _source, _settings: _clean_result())
    monkeypatch.setattr(
        vault,
        "validate_scanned_document",
        lambda _source, _media_type, _settings: None,
    )

    with pytest.raises(FileExistsError):
        _upload(settings)

    assert ciphertext.read_bytes() == b"existing-ciphertext"
    assert [path.name for path in version_path.iterdir()] == [vault.ENCRYPTED_NAME]


def test_runtime_probe_scrubs_private_legacy_orphan_and_scans_anonymous_inode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path)
    version_path = _make_private_version_path(settings)
    legacy = version_path / vault.LEGACY_PLAINTEXT_NAME
    legacy.write_bytes(PDF_BYTES)
    legacy.chmod(0o600)

    def scan(source, _settings):
        assert isinstance(source, PrivateObjectHandle)
        measured = os.fstat(source.descriptor)
        assert measured.st_nlink == 0
        assert stat.S_IMODE(measured.st_mode) == 0o600
        assert not legacy.exists()
        return _clean_result()

    monkeypatch.setattr(vault, "scan_private_object", scan)

    runtime = vault.staff_screening_evidence_runtime_status(settings)

    assert runtime.state == "ready"
    assert runtime.available is True
    assert not legacy.exists()
    assert not _vault_files(settings)


def test_runtime_probe_scrubs_legacy_orphan_even_when_key_is_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path)
    version_path = _make_private_version_path(settings)
    legacy = version_path / vault.LEGACY_PLAINTEXT_NAME
    legacy.write_bytes(PDF_BYTES)
    legacy.chmod(0o600)
    monkeypatch.setattr(
        vault,
        "_key",
        lambda _settings: (_ for _ in ()).throw(
            vault.ScannerUnavailable("staff_screening_vault_key_unavailable")
        ),
    )

    runtime = vault.staff_screening_evidence_runtime_status(settings)

    assert runtime.state == "unavailable"
    assert runtime.available is False
    assert not legacy.exists()


@pytest.mark.parametrize("legacy_kind", ["symlink", "hardlink", "public_file", "directory"])
def test_runtime_probe_refuses_suspicious_legacy_entries_without_touching_them(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    legacy_kind: str,
) -> None:
    settings = _settings(tmp_path)
    version_path = _make_private_version_path(settings)
    legacy = version_path / vault.LEGACY_PLAINTEXT_NAME
    sentinel = tmp_path / "sentinel"
    sentinel.write_bytes(b"must-not-be-touched")
    if legacy_kind == "symlink":
        legacy.symlink_to(sentinel)
    elif legacy_kind == "hardlink":
        legacy.write_bytes(PDF_BYTES)
        legacy.chmod(0o600)
        os.link(legacy, tmp_path / "second-link")
    elif legacy_kind == "public_file":
        legacy.write_bytes(PDF_BYTES)
        legacy.chmod(0o644)
    else:
        legacy.mkdir(mode=0o700)
    scanner_called = False

    def scan(_source, _settings):
        nonlocal scanner_called
        scanner_called = True
        return _clean_result()

    monkeypatch.setattr(vault, "scan_private_object", scan)

    runtime = vault.staff_screening_evidence_runtime_status(settings)

    assert runtime.state == "unavailable"
    assert runtime.available is False
    assert scanner_called is False
    assert os.path.lexists(legacy)
    assert sentinel.read_bytes() == b"must-not-be-touched"


def test_runtime_probe_refuses_symlinked_vault_component(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actual_parent = tmp_path / "actual"
    actual_parent.mkdir()
    linked_parent = tmp_path / "linked"
    linked_parent.symlink_to(actual_parent, target_is_directory=True)
    settings = _settings(tmp_path).model_copy(
        update={"staff_screening_vault_path": linked_parent / "screening-vault"}
    )
    scanner_called = False

    def scan(_source, _settings):
        nonlocal scanner_called
        scanner_called = True
        return _clean_result()

    monkeypatch.setattr(vault, "scan_private_object", scan)

    runtime = vault.staff_screening_evidence_runtime_status(settings)

    assert runtime.state == "unavailable"
    assert runtime.available is False
    assert scanner_called is False
    assert not (actual_parent / "screening-vault").exists()
