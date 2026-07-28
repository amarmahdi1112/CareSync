"""Recovery proofs for the encrypted 0030/0032 staff/transport vault."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import zipfile
from contextlib import contextmanager
from pathlib import Path

import pytest

import scripts.staff_transport_vault_bundle as bundle_module
from scripts.staff_transport_vault_bundle import (
    BUNDLE_FORMAT,
    StaffTransportVaultBundleError,
    create_staff_transport_vault_bundle,
    restore_staff_transport_vault_bundle,
    verify_staff_transport_vault_bundle,
)
from scripts.staff_transport_vault_preflight import StaffTransportVaultPreflightError
from tests.test_staff_transport_vault_preflight import (
    SCREENING_REFERENCE,
    SHARED_VEHICLE_REFERENCE,
    _create_backup,
    _create_vault,
    _fixture_rows,
)


def _bundle_fixture(
    tmp_path: Path,
) -> tuple[Path, Path, Path, Path, Path, dict[str, bytes]]:
    rows, objects = _fixture_rows()
    backup, manifest = _create_backup(tmp_path, rows)
    vault = _create_vault(tmp_path, objects)
    bundle, bundle_manifest = create_staff_transport_vault_bundle(
        backup,
        manifest,
        vault,
        tmp_path / "bundles",
    )
    return backup, manifest, vault, bundle, bundle_manifest, objects


def test_bundle_is_deterministic_private_and_restores_exact_ciphertext(
    tmp_path: Path,
) -> None:
    backup, manifest, _vault, bundle, bundle_manifest, objects = _bundle_fixture(tmp_path)

    verified = verify_staff_transport_vault_bundle(
        backup,
        manifest,
        bundle,
        bundle_manifest,
    )

    assert verified["uniqueObjectCount"] == 3
    assert verified["ownershipRelationshipCount"] == 5
    assert stat.S_IMODE(bundle.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(bundle.stat().st_mode) == 0o600
    assert stat.S_IMODE(bundle_manifest.stat().st_mode) == 0o600
    payload = json.loads(bundle_manifest.read_text(encoding="utf-8"))
    assert payload["format"] == BUNDLE_FORMAT
    assert payload["databaseVaultConsistencyAuthority"] is False
    assert payload["purgeAuthority"] is False
    assert payload["keyIdCounts"] == [
        {
            "encryptionKeyId": "staff-key-v1",
            "uniqueObjectCount": 2,
            "ownershipRelationshipCount": 2,
        },
        {
            "encryptionKeyId": "vehicle-key-v2",
            "uniqueObjectCount": 1,
            "ownershipRelationshipCount": 3,
        },
    ]
    assert {item["encryptionKeyId"] for item in payload["objects"]} == {
        "staff-key-v1",
        "vehicle-key-v2",
    }
    vehicle = next(
        item for item in payload["objects"] if item["storageReference"] == SHARED_VEHICLE_REFERENCE
    )
    assert [row["status"] for row in vehicle["ownershipRelationships"]] == [
        "provided",
        "expired",
        "revoked",
    ]

    second_bundle, second_manifest = create_staff_transport_vault_bundle(
        backup,
        manifest,
        _vault,
        tmp_path / "second-bundles",
    )
    assert (
        hashlib.sha256(second_bundle.read_bytes()).hexdigest()
        == hashlib.sha256(bundle.read_bytes()).hexdigest()
    )
    assert second_manifest.read_bytes() == bundle_manifest.read_bytes()

    destination = tmp_path / "disposable" / "staff-transport-vault"
    receipt = tmp_path / "receipts" / "staff-transport-restore.json"
    restored = restore_staff_transport_vault_bundle(
        backup,
        manifest,
        bundle,
        bundle_manifest,
        destination,
        receipt_path=receipt,
    )
    assert restored["restoredObjectCount"] == 3
    assert restored["ownershipRelationshipCount"] == 5
    assert stat.S_IMODE(destination.stat().st_mode) == 0o700
    assert stat.S_IMODE(receipt.stat().st_mode) == 0o600
    for reference, ciphertext in objects.items():
        target = destination.joinpath(*reference.split("/"))
        assert target.read_bytes() == ciphertext
        assert stat.S_IMODE(target.stat().st_mode) == 0o600

    with pytest.raises(StaffTransportVaultBundleError, match="already exists"):
        restore_staff_transport_vault_bundle(
            backup,
            manifest,
            bundle,
            bundle_manifest,
            destination,
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("missing", "does not exactly match"),
        ("mismatch", "does not exactly match"),
        ("unexpected", "does not exactly match"),
        ("link", "does not exactly match"),
        ("hardlink", "does not exactly match"),
        ("mode", "does not exactly match"),
        ("directory_mode", "does not exactly match"),
    ],
)
def test_create_rejects_incomplete_or_unsafe_live_vault(
    tmp_path: Path,
    mutation: str,
    message: str,
) -> None:
    rows, objects = _fixture_rows()
    backup, manifest = _create_backup(tmp_path, rows)
    vault = _create_vault(tmp_path, objects)
    screening = vault.joinpath(*SCREENING_REFERENCE.split("/"))
    if mutation == "missing":
        screening.unlink()
    elif mutation == "mismatch":
        screening.write_bytes(b"X" * len(objects[SCREENING_REFERENCE]))
        screening.chmod(0o600)
    elif mutation == "unexpected":
        unexpected = vault / "unexpected.enc"
        unexpected.write_bytes(b"not in backup")
        unexpected.chmod(0o600)
    elif mutation == "link":
        screening.unlink()
        screening.symlink_to(tmp_path / "outside")
    elif mutation == "hardlink":
        os.link(screening, vault / "unexpected-hardlink.enc")
    elif mutation == "directory_mode":
        screening.parent.chmod(0o755)
    else:
        screening.chmod(0o644)

    with pytest.raises(StaffTransportVaultBundleError, match=message):
        create_staff_transport_vault_bundle(
            backup,
            manifest,
            vault,
            tmp_path / "bundles",
        )

    output = tmp_path / "bundles"
    if output.exists():
        assert list(output.iterdir()) == []


def test_verify_rejects_archive_and_manifest_tamper(
    tmp_path: Path,
) -> None:
    backup, manifest, _vault, bundle, bundle_manifest, _objects = _bundle_fixture(tmp_path)
    original_bundle = bundle.read_bytes()
    original_manifest = bundle_manifest.read_bytes()

    with bundle.open("ab") as destination:
        destination.write(b"tamper")
    bundle.chmod(0o600)
    with pytest.raises(StaffTransportVaultBundleError, match="manifest differs"):
        verify_staff_transport_vault_bundle(
            backup,
            manifest,
            bundle,
            bundle_manifest,
        )

    bundle.write_bytes(original_bundle)
    bundle.chmod(0o600)
    payload = json.loads(original_manifest)
    payload["uniqueObjectCount"] += 1
    bundle_manifest.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    bundle_manifest.chmod(0o600)
    with pytest.raises(StaffTransportVaultBundleError, match="manifest differs"):
        verify_staff_transport_vault_bundle(
            backup,
            manifest,
            bundle,
            bundle_manifest,
        )


def test_verify_rejects_duplicate_member_even_with_recomputed_outer_hash(
    tmp_path: Path,
) -> None:
    backup, manifest, _vault, bundle, bundle_manifest, objects = _bundle_fixture(tmp_path)
    payload = json.loads(bundle_manifest.read_text(encoding="utf-8"))
    duplicate = tmp_path / "duplicate.zip"
    with (
        pytest.warns(UserWarning, match="Duplicate name"),
        zipfile.ZipFile(duplicate, "w", compression=zipfile.ZIP_STORED) as archive,
    ):
        for reference, content in objects.items():
            info = zipfile.ZipInfo(reference, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o600) << 16
            archive.writestr(info, content)
        reference = next(iter(objects))
        info = zipfile.ZipInfo(reference, date_time=(1980, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_STORED
        info.create_system = 3
        info.external_attr = (stat.S_IFREG | 0o600) << 16
        archive.writestr(info, objects[reference])
    duplicate.chmod(0o600)
    os.replace(duplicate, bundle)
    bundle.chmod(0o600)
    payload["sha256Bundle"] = hashlib.sha256(bundle.read_bytes()).hexdigest()
    bundle_manifest.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    bundle_manifest.chmod(0o600)

    with pytest.raises(StaffTransportVaultBundleError, match="inventory is not exact"):
        verify_staff_transport_vault_bundle(
            backup,
            manifest,
            bundle,
            bundle_manifest,
        )


def test_empty_inventory_allows_absent_vault_and_exact_empty_restore(
    tmp_path: Path,
) -> None:
    backup, manifest = _create_backup(tmp_path, [])
    absent_vault = tmp_path / "absent-vault"
    bundle, bundle_manifest = create_staff_transport_vault_bundle(
        backup,
        manifest,
        absent_vault,
        tmp_path / "bundles",
    )
    verified = verify_staff_transport_vault_bundle(
        backup,
        manifest,
        bundle,
        bundle_manifest,
    )
    assert verified["uniqueObjectCount"] == 0
    with zipfile.ZipFile(bundle, "r") as archive:
        assert archive.infolist() == []

    destination = tmp_path / "restored-empty-vault"
    result = restore_staff_transport_vault_bundle(
        backup,
        manifest,
        bundle,
        bundle_manifest,
        destination,
    )
    assert result["restoredObjectCount"] == 0
    assert destination.is_dir()
    assert list(destination.iterdir()) == []
    assert stat.S_IMODE(destination.stat().st_mode) == 0o700


def test_no_clobber_bundle_and_receipt(
    tmp_path: Path,
) -> None:
    backup, manifest, vault, bundle, bundle_manifest, _objects = _bundle_fixture(tmp_path)
    with pytest.raises(StaffTransportVaultBundleError, match="Refusing to replace"):
        create_staff_transport_vault_bundle(
            backup,
            manifest,
            vault,
            bundle.parent,
        )

    receipt = tmp_path / "receipts" / "restore.json"
    receipt.parent.mkdir(mode=0o700)
    receipt.parent.chmod(0o700)
    receipt.write_text("keep", encoding="utf-8")
    receipt.chmod(0o600)
    with pytest.raises(StaffTransportVaultBundleError, match="receipt already exists"):
        restore_staff_transport_vault_bundle(
            backup,
            manifest,
            bundle,
            bundle_manifest,
            tmp_path / "restore-must-not-exist",
            receipt_path=receipt,
        )
    assert receipt.read_text(encoding="utf-8") == "keep"
    assert not (tmp_path / "restore-must-not-exist").exists()


def test_restore_removes_its_new_root_and_receipt_if_pinned_backup_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backup, manifest, _vault, bundle, bundle_manifest, _objects = _bundle_fixture(tmp_path)
    original_context = bundle_module.pinned_staff_transport_inventory

    @contextmanager
    def fail_after_use(backup_path: Path, manifest_path: Path):
        with original_context(backup_path, manifest_path) as projection:
            yield projection
        raise StaffTransportVaultPreflightError(
            "Verified database backup artifacts changed during inventory use"
        )

    monkeypatch.setattr(
        bundle_module,
        "pinned_staff_transport_inventory",
        fail_after_use,
    )
    destination = tmp_path / "restore-must-be-removed"
    receipt = tmp_path / "receipts" / "receipt-must-be-removed.json"

    with pytest.raises(StaffTransportVaultBundleError, match="changed during inventory use"):
        restore_staff_transport_vault_bundle(
            backup,
            manifest,
            bundle,
            bundle_manifest,
            destination,
            receipt_path=receipt,
        )

    assert not destination.exists()
    assert not receipt.exists()
