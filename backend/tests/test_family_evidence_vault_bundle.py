"""Backup/restore gates for the private 0029A1 evidence-object vault."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import zipfile
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import create_engine, text

from scripts.backup_database import _sha256_file, create_backup
from scripts.family_evidence_vault_bundle import (
    EvidenceVaultBundleError,
    _validate_storage_reference,
    create_evidence_bundle,
    restore_evidence_bundle,
    verify_evidence_bundle,
)

ORGANIZATION_ID = UUID("11111111-1111-4111-8111-111111111111")
FAMILY_ID = UUID("22222222-2222-4222-8222-222222222222")
CLEAN_ID = UUID("33333333-3333-4333-8333-333333333333")
QUARANTINED_ID = UUID("44444444-4444-4444-8444-444444444444")
MALWARE_ID = UUID("55555555-5555-4555-8555-555555555555")
INVALID_DOCUMENT_ID = UUID("66666666-6666-4666-8666-666666666666")


def _reference(object_id: UUID) -> str:
    return f"{ORGANIZATION_ID.hex}/{FAMILY_ID.hex}/{object_id.hex}/v1.pdf"


@pytest.mark.parametrize(
    "reference",
    [
        f"{ORGANIZATION_ID.hex}//{FAMILY_ID.hex}/{CLEAN_ID.hex}/v1.pdf",
        f"{ORGANIZATION_ID.hex}/./{FAMILY_ID.hex}/{CLEAN_ID.hex}/v1.pdf",
    ],
)
def test_storage_reference_rejects_normalized_but_noncanonical_spelling(reference: str) -> None:
    with pytest.raises(EvidenceVaultBundleError, match="opaque v1 key"):
        _validate_storage_reference(
            reference,
            organization_id=str(ORGANIZATION_ID),
            family_id=str(FAMILY_ID),
            object_id=str(CLEAN_ID),
            media_type="application/pdf",
        )


OBJECT_BYTES = {
    CLEAN_ID: b"%PDF-1.7 clean evidence\n",
    QUARANTINED_ID: b"%PDF-1.7 quarantined evidence\n",
    MALWARE_ID: b"%PDF-1.7 malware bytes are never bundled\n",
    INVALID_DOCUMENT_ID: b"%PDF-1.7 structurally invalid but non-malware evidence\n",
}
OBJECT_STATES = {
    CLEAN_ID: ("clean", None),
    QUARANTINED_ID: ("quarantined", None),
    MALWARE_ID: ("rejected", "malware_detected"),
    INVALID_DOCUMENT_ID: ("rejected", "invalid_document"),
}


def _create_database_backup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    database_path = tmp_path / "caresync.db"
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE alembic_version (version_num TEXT PRIMARY KEY)"))
            connection.execute(
                text("INSERT INTO alembic_version VALUES ('0029A1_family_evidence_vault')")
            )
            connection.execute(
                text(
                    "CREATE TABLE family_authority_evidence_objects ("
                    "id TEXT PRIMARY KEY, organization_id TEXT NOT NULL, "
                    "family_id TEXT NOT NULL, evidence_kind TEXT NOT NULL, "
                    "object_version INTEGER NOT NULL, storage_reference TEXT NOT NULL, "
                    "media_type TEXT NOT NULL, byte_size INTEGER NOT NULL, "
                    "content_sha256 TEXT NOT NULL, status TEXT NOT NULL)"
                )
            )
            connection.execute(
                text(
                    "CREATE TABLE family_authority_evidence_object_assessments ("
                    "id TEXT PRIMARY KEY, organization_id TEXT NOT NULL, "
                    "family_id TEXT NOT NULL, evidence_object_id TEXT NOT NULL, "
                    "version_number INTEGER NOT NULL, decision TEXT NOT NULL, "
                    "reason_code TEXT)"
                )
            )
            assessment_number = 0
            for object_id, (status_value, reason) in OBJECT_STATES.items():
                content = OBJECT_BYTES[object_id]
                connection.execute(
                    text(
                        "INSERT INTO family_authority_evidence_objects "
                        "(id,organization_id,family_id,evidence_kind,object_version,"
                        "storage_reference,media_type,byte_size,content_sha256,status) "
                        "VALUES (:id,:organization_id,:family_id,:evidence_kind,1,"
                        ":storage_reference,'application/pdf',:byte_size,:content_sha256,:status)"
                    ),
                    {
                        "id": str(object_id),
                        "organization_id": str(ORGANIZATION_ID),
                        "family_id": str(FAMILY_ID),
                        "evidence_kind": (
                            "signed_release_delegation" if object_id == CLEAN_ID else "court_order"
                        ),
                        "storage_reference": _reference(object_id),
                        "byte_size": len(content),
                        "content_sha256": hashlib.sha256(content).hexdigest(),
                        "status": status_value,
                    },
                )
                assessment_number += 1
                connection.execute(
                    text(
                        "INSERT INTO family_authority_evidence_object_assessments "
                        "(id,organization_id,family_id,evidence_object_id,version_number,"
                        "decision,reason_code) VALUES (:id,:organization_id,:family_id,"
                        ":object_id,1,'quarantined',NULL)"
                    ),
                    {
                        "id": f"00000000-0000-4000-8000-{assessment_number:012d}",
                        "organization_id": str(ORGANIZATION_ID),
                        "family_id": str(FAMILY_ID),
                        "object_id": str(object_id),
                    },
                )
                if status_value != "quarantined":
                    assessment_number += 1
                    connection.execute(
                        text(
                            "INSERT INTO family_authority_evidence_object_assessments "
                            "(id,organization_id,family_id,evidence_object_id,version_number,"
                            "decision,reason_code) VALUES (:id,:organization_id,:family_id,"
                            ":object_id,2,:decision,:reason_code)"
                        ),
                        {
                            "id": f"00000000-0000-4000-8000-{assessment_number:012d}",
                            "organization_id": str(ORGANIZATION_ID),
                            "family_id": str(FAMILY_ID),
                            "object_id": str(object_id),
                            "decision": status_value,
                            "reason_code": reason,
                        },
                    )
    finally:
        engine.dispose()

    monkeypatch.setenv("DATABASE_TYPE", "sqlite")
    monkeypatch.setenv("DATABASE_PATH", str(database_path))
    monkeypatch.setenv("DATABASE_NAME", "caresync")
    return create_backup(tmp_path / "database-backups")


def _create_vault(tmp_path: Path) -> Path:
    root = tmp_path / "private-vault"
    root.mkdir(mode=0o700)
    root.chmod(0o700)
    for object_id, content in OBJECT_BYTES.items():
        path = root.joinpath(*_reference(object_id).split("/"))
        path.parent.mkdir(parents=True, mode=0o700)
        cursor = path.parent
        while cursor != root:
            cursor.chmod(0o700)
            cursor = cursor.parent
        path.write_bytes(content)
        path.chmod(0o600)
    return root


def _create_bundle_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path, Path, Path, Path]:
    backup, manifest = _create_database_backup(tmp_path, monkeypatch)
    vault = _create_vault(tmp_path)
    bundle, bundle_manifest = create_evidence_bundle(
        backup,
        manifest,
        vault,
        tmp_path / "evidence-backups",
    )
    return backup, manifest, vault, bundle, bundle_manifest


def test_bundle_inventory_is_db_derived_and_disposable_restore_is_exact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backup, manifest, _, bundle, bundle_manifest = _create_bundle_fixture(tmp_path, monkeypatch)

    verified = verify_evidence_bundle(backup, manifest, bundle, bundle_manifest)
    assert verified["objectCount"] == 4
    assert verified["includedObjectCount"] == 4
    assert verified["rejectedObjectCount"] == 2
    assert stat.S_IMODE(bundle.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(bundle.stat().st_mode) == 0o600
    assert stat.S_IMODE(bundle_manifest.stat().st_mode) == 0o600
    assert {item["disposition"] for item in verified["objects"]} == {"included"}
    assert {
        item["evidenceKind"] for item in verified["objects"] if item["objectId"] == str(CLEAN_ID)
    } == {"signed_release_delegation"}

    destination = tmp_path / "disposable" / "restored-vault"
    receipt = tmp_path / "receipts" / "evidence-restore.json"
    result = restore_evidence_bundle(
        backup,
        manifest,
        bundle,
        bundle_manifest,
        destination,
        receipt_path=receipt,
    )
    assert result["restoredObjectCount"] == 4
    assert result["rejectedObjectCount"] == 2
    assert stat.S_IMODE(destination.stat().st_mode) == 0o700
    assert stat.S_IMODE(receipt.stat().st_mode) == 0o600
    for object_id in (CLEAN_ID, QUARANTINED_ID, MALWARE_ID, INVALID_DOCUMENT_ID):
        restored = destination.joinpath(*_reference(object_id).split("/"))
        assert restored.read_bytes() == OBJECT_BYTES[object_id]
        assert stat.S_IMODE(restored.stat().st_mode) == 0o600

    with pytest.raises(EvidenceVaultBundleError, match="destination already exists"):
        restore_evidence_bundle(
            backup,
            manifest,
            bundle,
            bundle_manifest,
            destination,
        )


def test_bundle_creation_rejects_missing_or_changed_required_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backup, manifest = _create_database_backup(tmp_path, monkeypatch)
    vault = _create_vault(tmp_path)
    clean_path = vault.joinpath(*_reference(CLEAN_ID).split("/"))
    clean_path.write_bytes(b"%PDF-tampered")
    clean_path.chmod(0o600)

    with pytest.raises(EvidenceVaultBundleError, match="measurements do not match"):
        create_evidence_bundle(
            backup,
            manifest,
            vault,
            tmp_path / "evidence-backups",
        )

    clean_path.unlink()
    with pytest.raises(EvidenceVaultBundleError, match="Required evidence bytes are absent"):
        create_evidence_bundle(
            backup,
            manifest,
            vault,
            tmp_path / "evidence-backups-2",
        )


def test_bundle_creation_requires_rejected_malware_bytes_to_remain_complete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backup, manifest = _create_database_backup(tmp_path, monkeypatch)
    vault = _create_vault(tmp_path)
    vault.joinpath(*_reference(MALWARE_ID).split("/")).unlink()

    with pytest.raises(EvidenceVaultBundleError, match="Required evidence bytes are absent"):
        create_evidence_bundle(
            backup,
            manifest,
            vault,
            tmp_path / "evidence-backups",
        )


def test_bundle_creation_rejects_source_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backup, manifest = _create_database_backup(tmp_path, monkeypatch)
    vault = _create_vault(tmp_path)
    clean_path = vault.joinpath(*_reference(CLEAN_ID).split("/"))
    safe_target = tmp_path / "outside.pdf"
    safe_target.write_bytes(OBJECT_BYTES[CLEAN_ID])
    safe_target.chmod(0o600)
    clean_path.unlink()
    clean_path.symlink_to(safe_target)

    with pytest.raises(EvidenceVaultBundleError, match="symbolic link"):
        create_evidence_bundle(
            backup,
            manifest,
            vault,
            tmp_path / "evidence-backups",
        )


def test_bundle_publish_collision_never_deletes_the_winner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backup, manifest = _create_database_backup(tmp_path, monkeypatch)
    vault = _create_vault(tmp_path)
    output = tmp_path / "evidence-backups"
    winner = b"independent-winner"

    def publish_winner_then_collide(
        source: os.PathLike[str] | str,
        destination: os.PathLike[str] | str,
        *,
        follow_symlinks: bool = True,
    ) -> None:
        del source, follow_symlinks
        target = Path(destination)
        target.write_bytes(winner)
        target.chmod(0o600)
        raise FileExistsError("synthetic competing publisher")

    monkeypatch.setattr(os, "link", publish_winner_then_collide)
    with pytest.raises(EvidenceVaultBundleError, match="Refusing to replace"):
        create_evidence_bundle(backup, manifest, vault, output)

    bundle = output / f"{backup.name.removesuffix('.json.gz')}.family-evidence.zip"
    assert bundle.read_bytes() == winner
    assert stat.S_IMODE(bundle.stat().st_mode) == 0o600
    assert not bundle.with_suffix(".manifest.json").exists()
    assert not list(output.glob("*.partial-*"))


def test_verification_rejects_extra_traversal_member_even_with_updated_outer_digest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backup, manifest, _, bundle, bundle_manifest = _create_bundle_fixture(tmp_path, monkeypatch)
    with zipfile.ZipFile(bundle, "a", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("../escape", b"not allowed")
    bundle.chmod(0o600)
    value = json.loads(bundle_manifest.read_text(encoding="utf-8"))
    value["sha256Bundle"] = _sha256_file(bundle)
    bundle_manifest.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    bundle_manifest.chmod(0o600)

    with pytest.raises(EvidenceVaultBundleError, match="member inventory"):
        verify_evidence_bundle(backup, manifest, bundle, bundle_manifest)
    assert not (tmp_path / "escape").exists()


def test_verification_rejects_archive_symlink_for_an_expected_object(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backup, manifest, _, bundle, bundle_manifest = _create_bundle_fixture(tmp_path, monkeypatch)
    with zipfile.ZipFile(bundle, "r") as source:
        members = {info.filename: source.read(info) for info in source.infolist()}
    replacement = bundle.with_name("replacement.zip")
    with zipfile.ZipFile(replacement, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, content in members.items():
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.compress_type = zipfile.ZIP_STORED
            if name == _reference(CLEAN_ID):
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                content = b"../../outside"
            else:
                info.external_attr = (stat.S_IFREG | 0o600) << 16
            archive.writestr(info, content)
    replacement.chmod(0o600)
    os.replace(replacement, bundle)
    bundle.chmod(0o600)
    value = json.loads(bundle_manifest.read_text(encoding="utf-8"))
    value["sha256Bundle"] = _sha256_file(bundle)
    bundle_manifest.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    bundle_manifest.chmod(0o600)

    with pytest.raises(EvidenceVaultBundleError, match="unsafe member"):
        verify_evidence_bundle(backup, manifest, bundle, bundle_manifest)


def test_restore_rejects_symlinked_parent_and_receipt_inside_vault(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backup, manifest, _, bundle, bundle_manifest = _create_bundle_fixture(tmp_path, monkeypatch)
    real_parent = tmp_path / "real-parent"
    real_parent.mkdir(mode=0o700)
    real_parent.chmod(0o700)
    linked_parent = tmp_path / "linked-parent"
    linked_parent.symlink_to(real_parent, target_is_directory=True)

    with pytest.raises(EvidenceVaultBundleError, match="symbolic link"):
        restore_evidence_bundle(
            backup,
            manifest,
            bundle,
            bundle_manifest,
            linked_parent / "restored-vault",
        )

    destination = tmp_path / "safe-parent" / "restored-vault"
    with pytest.raises(EvidenceVaultBundleError, match="inside the vault"):
        restore_evidence_bundle(
            backup,
            manifest,
            bundle,
            bundle_manifest,
            destination,
            receipt_path=destination / "receipt.json",
        )
    assert not destination.exists()


def test_verification_rejects_database_backup_substitution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backup, manifest, _, bundle, bundle_manifest = _create_bundle_fixture(
        tmp_path / "first", monkeypatch
    )
    second_backup, second_manifest = _create_database_backup(tmp_path / "second", monkeypatch)

    with pytest.raises(EvidenceVaultBundleError, match="different database backup"):
        verify_evidence_bundle(
            second_backup,
            second_manifest,
            bundle,
            bundle_manifest,
        )

    verify_evidence_bundle(backup, manifest, bundle, bundle_manifest)
