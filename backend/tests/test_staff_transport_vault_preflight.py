"""Backup-bound proofs for the report-only encrypted staff-vault preflight."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import stat
from collections import Counter
from pathlib import Path
from uuid import UUID

import pytest

import scripts.staff_transport_vault_preflight as preflight_module
from scripts.backup_database import BACKUP_FORMAT, encode_value
from scripts.staff_transport_vault_preflight import (
    BLOCKER,
    ENCRYPTED_CONTAINER_OVERHEAD_BYTES,
    EVIDENCE_TABLES,
    StaffTransportVaultPreflightError,
    preflight_staff_transport_vault,
    write_preflight_receipt,
)

USER_A = UUID("11111111-1111-4111-8111-111111111111")
USER_B = UUID("22222222-2222-4222-8222-222222222222")
REVIEWER = UUID("33333333-3333-4333-8333-333333333333")
ORGANIZATION = UUID("44444444-4444-4444-8444-444444444444")
MEMBERSHIP = UUID("55555555-5555-4555-8555-555555555555")
SCREENING_VERSION = UUID("66666666-6666-4666-8666-666666666666")
QUALIFICATION = UUID("77777777-7777-4777-8777-777777777777")
QUALIFICATION_EVIDENCE = UUID("88888888-8888-4888-8888-888888888888")
VEHICLE = UUID("99999999-9999-4999-8999-999999999999")
VEHICLE_VERSION = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
VEHICLE_EVIDENCE_A = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
VEHICLE_EVIDENCE_B = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
VEHICLE_STORAGE_TOKEN = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
QUALIFICATION_STORAGE_TOKEN = UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee")
VEHICLE_EVIDENCE_C = UUID("ffffffff-ffff-4fff-8fff-ffffffffffff")


def _reference(first: UUID, second: UUID, third: UUID) -> str:
    return f"{first.hex}/{second.hex}/{third.hex}/v1.enc"


SCREENING_REFERENCE = _reference(USER_A, MEMBERSHIP, SCREENING_VERSION)
QUALIFICATION_REFERENCE = _reference(USER_A, MEMBERSHIP, QUALIFICATION_STORAGE_TOKEN)
SHARED_VEHICLE_REFERENCE = _reference(USER_B, VEHICLE, VEHICLE_STORAGE_TOKEN)


def _encoded_row(value: dict) -> dict:
    return {key: encode_value(item) for key, item in value.items()}


def _metadata(plaintext: bytes, ciphertext: bytes, key_id: str) -> dict:
    assert len(ciphertext) == len(plaintext) + ENCRYPTED_CONTAINER_OVERHEAD_BYTES
    return {
        "media_type": "application/pdf",
        "byte_size": len(plaintext),
        "content_sha256": hashlib.sha256(plaintext).hexdigest(),
        "ciphertext_sha256": hashlib.sha256(ciphertext).hexdigest(),
        "encryption_key_id": key_id,
    }


def _fixture_rows() -> tuple[list[tuple[str, dict]], dict[str, bytes]]:
    staff_plaintext = b"staff screening plaintext measurement"
    staff_ciphertext = b"S" * (len(staff_plaintext) + ENCRYPTED_CONTAINER_OVERHEAD_BYTES)
    qualification_ciphertext = b"Q" * (len(staff_plaintext) + ENCRYPTED_CONTAINER_OVERHEAD_BYTES)
    vehicle_plaintext = b"vehicle evidence plaintext measurement"
    vehicle_ciphertext = b"V" * (len(vehicle_plaintext) + ENCRYPTED_CONTAINER_OVERHEAD_BYTES)
    staff_metadata = _metadata(staff_plaintext, staff_ciphertext, "staff-key-v1")
    qualification_metadata = _metadata(
        staff_plaintext,
        qualification_ciphertext,
        "staff-key-v1",
    )
    vehicle_metadata = _metadata(vehicle_plaintext, vehicle_ciphertext, "vehicle-key-v2")
    rows = [
        (
            "staff_screening_document_versions",
            {
                "id": SCREENING_VERSION,
                "document_id": MEMBERSHIP,
                "user_id": USER_A,
                "version_number": 1,
                "storage_reference": SCREENING_REFERENCE,
                **staff_metadata,
            },
        ),
        (
            "staff_driver_qualification_evidence_objects",
            {
                "id": QUALIFICATION_EVIDENCE,
                "organization_id": ORGANIZATION,
                "membership_id": MEMBERSHIP,
                "qualification_version_id": QUALIFICATION,
                "recorded_by_user_id": USER_A,
                "storage_reference": QUALIFICATION_REFERENCE,
                **qualification_metadata,
            },
        ),
        (
            "transport_vehicle_evidence_versions",
            {
                "id": VEHICLE_EVIDENCE_A,
                "organization_id": ORGANIZATION,
                "vehicle_id": VEHICLE,
                "vehicle_version_id": VEHICLE_VERSION,
                "evidence_type": "insurance",
                "version_number": 1,
                "status": "provided",
                "recorded_by_user_id": USER_B,
                "storage_reference": SHARED_VEHICLE_REFERENCE,
                **vehicle_metadata,
            },
        ),
        (
            "transport_vehicle_evidence_versions",
            {
                "id": VEHICLE_EVIDENCE_B,
                "organization_id": ORGANIZATION,
                "vehicle_id": VEHICLE,
                "vehicle_version_id": VEHICLE_VERSION,
                "evidence_type": "insurance",
                "version_number": 2,
                "status": "expired",
                "recorded_by_user_id": REVIEWER,
                "storage_reference": SHARED_VEHICLE_REFERENCE,
                **vehicle_metadata,
            },
        ),
        (
            "transport_vehicle_evidence_versions",
            {
                "id": VEHICLE_EVIDENCE_C,
                "organization_id": ORGANIZATION,
                "vehicle_id": VEHICLE,
                "vehicle_version_id": VEHICLE_VERSION,
                "evidence_type": "insurance",
                "version_number": 3,
                "status": "revoked",
                "recorded_by_user_id": REVIEWER,
                "storage_reference": SHARED_VEHICLE_REFERENCE,
                **vehicle_metadata,
            },
        ),
    ]
    return rows, {
        SCREENING_REFERENCE: staff_ciphertext,
        QUALIFICATION_REFERENCE: qualification_ciphertext,
        SHARED_VEHICLE_REFERENCE: vehicle_ciphertext,
    }


def _create_backup(
    tmp_path: Path,
    rows: list[tuple[str, dict]],
) -> tuple[Path, Path]:
    directory = tmp_path / "backup"
    directory.mkdir(mode=0o700)
    directory.chmod(0o700)
    counts = Counter(table for table, _row in rows)
    table_counts = {table: counts[table] for table in EVIDENCE_TABLES}
    header = {
        "format": BACKUP_FORMAT,
        "databaseName": "caresync",
        "databaseType": "postgres",
        "createdAt": "2026-07-21T18:00:00+00:00",
        "tables": list(EVIDENCE_TABLES),
        "directTableCounts": table_counts,
        "alembicRevisions": ["0032_transport_registry_commands"],
        "visibilityMode": "row_security_off_complete",
        "snapshot": "verified-test-snapshot",
    }
    lines = [json.dumps({"header": header}, separators=(",", ":"), sort_keys=True) + "\n"]
    for table, row in rows:
        lines.append(
            json.dumps(
                {"table": table, "row": _encoded_row(row)},
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
        )
    backup = directory / "caresync-postgres-test.json.gz"
    with gzip.open(backup, "wt", encoding="utf-8") as destination:
        destination.writelines(lines)
    backup.chmod(0o600)
    all_lines = "".join(lines).encode()
    row_lines = "".join(lines[1:]).encode()
    manifest = backup.with_suffix(".manifest.json")
    manifest.write_text(
        json.dumps(
            {
                "format": BACKUP_FORMAT,
                "backup": backup.name,
                "sha256Compressed": hashlib.sha256(backup.read_bytes()).hexdigest(),
                "sha256UncompressedJsonLines": hashlib.sha256(all_lines).hexdigest(),
                "sha256Rows": hashlib.sha256(row_lines).hexdigest(),
                "tableCounts": table_counts,
                "totalRows": len(rows),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    manifest.chmod(0o600)
    return backup, manifest


def _write_private(root: Path, reference: str, content: bytes) -> Path:
    path = root.joinpath(*reference.split("/"))
    path.parent.mkdir(parents=True, mode=0o700)
    cursor = path.parent
    while cursor != root:
        cursor.chmod(0o700)
        cursor = cursor.parent
    path.write_bytes(content)
    path.chmod(0o600)
    return path


def _create_vault(tmp_path: Path, objects: dict[str, bytes]) -> Path:
    vault = tmp_path / "staff-vault"
    vault.mkdir(mode=0o700)
    vault.chmod(0o700)
    for reference, content in objects.items():
        _write_private(vault, reference, content)
    return vault


def test_preflight_deduplicates_shared_refs_and_writes_private_receipt(
    tmp_path: Path,
) -> None:
    rows, objects = _fixture_rows()
    backup, manifest = _create_backup(tmp_path, rows)
    vault = _create_vault(tmp_path, objects)

    report = preflight_staff_transport_vault(backup, manifest, vault)

    assert report["format"] == "caresync-staff-transport-vault-preflight-v1"
    assert report["mode"] == "report_only"
    assert report["expectedCount"] == report["presentCount"] == 3
    assert report["missing"] == report["mismatch"] == []
    assert report["unsafe"] == report["unexpected"] == report["indeterminate"] == []
    assert report["inventory"]["uniqueObjectCount"] == 3
    assert report["inventory"]["ownershipRelationshipCount"] == 5
    assert report["inventory"]["sourceRowCounts"] == {
        "staff_screening_document_versions": 1,
        "staff_driver_qualification_evidence_objects": 1,
        "transport_vehicle_evidence_versions": 3,
    }
    assert report["inventory"]["keyIdCounts"] == [
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
    vehicle_object = next(
        item
        for item in report["inventory"]["objects"]
        if item["storageReference"] == SHARED_VEHICLE_REFERENCE
    )
    assert [value["status"] for value in vehicle_object["ownershipRelationships"]] == [
        "provided",
        "expired",
        "revoked",
    ]
    assert vehicle_object["ownershipRelationships"][0]["storageNamespaceUserId"] == str(USER_B)
    assert report["databaseBackup"]["alembicRevisions"] == ["0032_transport_registry_commands"]
    assert len(report["databaseBackup"]["sha256Compressed"]) == 64
    assert len(report["databaseBackup"]["sha256Manifest"]) == 64
    assert len(report["databaseBackup"]["sha256Rows"]) == 64
    assert report["consistencyAuthority"] is False
    assert report["purgeAuthority"] is False
    assert report["blocker"] == BLOCKER

    receipt_directory = tmp_path / "receipts"
    receipt_directory.mkdir(mode=0o700)
    receipt = receipt_directory / "preflight.json"
    write_preflight_receipt(receipt, report)
    assert stat.S_IMODE(receipt.stat().st_mode) == 0o600
    assert json.loads(receipt.read_text(encoding="utf-8")) == report
    with pytest.raises(StaffTransportVaultPreflightError, match="Refusing to replace"):
        write_preflight_receipt(receipt, report)


def test_conflicting_shared_reference_metadata_fails_before_vault_scan(
    tmp_path: Path,
) -> None:
    rows, _objects = _fixture_rows()
    rows[3][1]["ciphertext_sha256"] = "f" * 64
    backup, manifest = _create_backup(tmp_path, rows)
    absent_vault = tmp_path / "must-not-be-created"

    with pytest.raises(StaffTransportVaultPreflightError, match="conflicting metadata"):
        preflight_staff_transport_vault(backup, manifest, absent_vault)

    assert not absent_vault.exists()


def test_cross_table_reference_alias_is_rejected(
    tmp_path: Path,
) -> None:
    rows, _objects = _fixture_rows()
    rows[1][1]["storage_reference"] = SCREENING_REFERENCE
    for field in (
        "media_type",
        "byte_size",
        "content_sha256",
        "ciphertext_sha256",
        "encryption_key_id",
    ):
        rows[1][1][field] = rows[0][1][field]
    backup, manifest = _create_backup(tmp_path, rows)

    with pytest.raises(StaffTransportVaultPreflightError, match="across source tables"):
        preflight_staff_transport_vault(backup, manifest, tmp_path / "absent")


def test_non_vehicle_reference_cannot_have_multiple_source_rows(
    tmp_path: Path,
) -> None:
    rows, _objects = _fixture_rows()
    rows.append(
        (
            "staff_driver_qualification_evidence_objects",
            {
                **rows[1][1],
                "id": VEHICLE_EVIDENCE_A,
                "qualification_version_id": VEHICLE_VERSION,
            },
        )
    )
    backup, manifest = _create_backup(tmp_path, rows)

    with pytest.raises(StaffTransportVaultPreflightError, match="multiple source rows"):
        preflight_staff_transport_vault(backup, manifest, tmp_path / "absent")


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("no_provided_source", "namespace-bound source"),
        ("source_namespace_mismatch", "namespace-bound source"),
        ("ownership_mismatch", "conflicting ownership"),
    ],
)
def test_vehicle_shared_reference_requires_one_coherent_namespace_bound_source(
    tmp_path: Path,
    case: str,
    message: str,
) -> None:
    rows, _objects = _fixture_rows()
    if case == "no_provided_source":
        rows[2][1]["status"] = "verified"
    elif case == "source_namespace_mismatch":
        rows[2][1]["recorded_by_user_id"] = REVIEWER
    else:
        rows[3][1]["vehicle_version_id"] = QUALIFICATION
    backup, manifest = _create_backup(tmp_path, rows)

    with pytest.raises(StaffTransportVaultPreflightError, match=message):
        preflight_staff_transport_vault(backup, manifest, tmp_path / "absent")


def test_inventory_parse_rejects_swap_read_and_swap_back_race(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows, objects = _fixture_rows()
    backup, manifest = _create_backup(tmp_path, rows)
    vault = _create_vault(tmp_path, objects)

    malicious_root = tmp_path / "malicious"
    malicious_root.mkdir(mode=0o700)
    malicious_rows, _malicious_objects = _fixture_rows()
    malicious_rows[0][1]["storage_reference"] = _reference(
        USER_A,
        MEMBERSHIP,
        QUALIFICATION,
    )
    malicious_backup, _malicious_manifest = _create_backup(
        malicious_root,
        malicious_rows,
    )
    staged_attack = backup.parent / "staged-attack.json.gz"
    malicious_backup.rename(staged_attack)
    held_original = backup.parent / "held-original.json.gz"
    original_derive = preflight_module._derive_inventory
    swapped = False

    def swap_around_pinned_read(artifact, verified):
        nonlocal swapped
        backup.rename(held_original)
        staged_attack.rename(backup)
        swapped = True
        try:
            return original_derive(artifact, verified)
        finally:
            backup.rename(staged_attack)
            held_original.rename(backup)

    monkeypatch.setattr(
        preflight_module,
        "_derive_inventory",
        swap_around_pinned_read,
    )

    with pytest.raises(StaffTransportVaultPreflightError, match="changed while pinned"):
        preflight_staff_transport_vault(backup, manifest, vault)

    assert swapped is True
    assert backup.exists()
    assert not held_original.exists()


def test_noncanonical_database_reference_fails_closed(
    tmp_path: Path,
) -> None:
    rows, _objects = _fixture_rows()
    rows[0][1]["storage_reference"] = "transport/private/insurance.enc"
    backup, manifest = _create_backup(tmp_path, rows)

    with pytest.raises(StaffTransportVaultPreflightError, match="canonical v1.enc"):
        preflight_staff_transport_vault(backup, manifest, tmp_path / "absent")


def test_report_classifies_missing_mismatch_unsafe_and_unexpected_without_following(
    tmp_path: Path,
) -> None:
    rows, objects = _fixture_rows()
    backup, manifest = _create_backup(tmp_path, rows)
    vault = _create_vault(tmp_path, objects)
    vault.joinpath(*SCREENING_REFERENCE.split("/")).unlink()
    vehicle_path = vault.joinpath(*SHARED_VEHICLE_REFERENCE.split("/"))
    vehicle_path.write_bytes(b"X" * len(objects[SHARED_VEHICLE_REFERENCE]))
    vehicle_path.chmod(0o600)

    unexpected_reference = _reference(REVIEWER, MEMBERSHIP, QUALIFICATION_EVIDENCE)
    unexpected = _write_private(vault, unexpected_reference, b"U" * 64)
    outside = tmp_path / "outside"
    outside.mkdir(mode=0o700)
    sentinel = outside / "sentinel.enc"
    sentinel.write_bytes(b"outside bytes must not be read through the link")
    sentinel.chmod(0o600)
    (vault / "linked-outside").symlink_to(outside, target_is_directory=True)

    report = preflight_staff_transport_vault(backup, manifest, vault)

    assert report["missing"] == [SCREENING_REFERENCE]
    assert report["mismatch"] == [
        {
            "reference": SHARED_VEHICLE_REFERENCE,
            "reason": "ciphertext_sha256_mismatch",
        }
    ]
    assert {item["reason"] for item in report["unsafe"]} >= {"symbolic_link"}
    unexpected_file = next(
        item
        for item in report["unexpected"]
        if item["reference"] == unexpected_reference and item["kind"] == "file"
    )
    assert unexpected_file["canonical"] is True
    assert (
        unexpected_file["measurement"]["ciphertextSha256"]
        == hashlib.sha256(unexpected.read_bytes()).hexdigest()
    )
    assert report["consistencyAuthority"] is False
    assert report["purgeAuthority"] is False
    assert sentinel.read_bytes() == b"outside bytes must not be read through the link"


def test_concurrent_ciphertext_change_is_indeterminate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows, objects = _fixture_rows()
    backup, manifest = _create_backup(tmp_path, rows)
    vault = _create_vault(tmp_path, objects)
    target = vault.joinpath(*SCREENING_REFERENCE.split("/"))
    target_identity = (target.stat().st_dev, target.stat().st_ino)
    original_read = os.read
    changed = False

    def racing_read(descriptor: int, amount: int) -> bytes:
        nonlocal changed
        chunk = original_read(descriptor, amount)
        details = os.fstat(descriptor)
        if chunk and not changed and (details.st_dev, details.st_ino) == target_identity:
            changed = True
            with target.open("ab") as destination:
                destination.write(b"concurrent change")
        return chunk

    monkeypatch.setattr(preflight_module.os, "read", racing_read)

    report = preflight_staff_transport_vault(backup, manifest, vault)

    assert changed is True
    assert {
        "reference": SCREENING_REFERENCE,
        "reason": "concurrent_file_change",
    } in report["indeterminate"]
    assert report["presentCount"] == 2
    assert report["consistencyAuthority"] is False


def test_tampered_backup_symlinked_vault_and_receipt_inside_vault_fail_closed(
    tmp_path: Path,
) -> None:
    rows, objects = _fixture_rows()
    backup, manifest = _create_backup(tmp_path, rows)
    vault = _create_vault(tmp_path, objects)
    linked_vault = tmp_path / "linked-vault"
    linked_vault.symlink_to(vault, target_is_directory=True)

    with pytest.raises(StaffTransportVaultPreflightError, match="symbolic-link"):
        preflight_staff_transport_vault(backup, manifest, linked_vault)

    report = preflight_staff_transport_vault(backup, manifest, vault)
    with pytest.raises(StaffTransportVaultPreflightError, match="inside the evidence vault"):
        write_preflight_receipt(vault / "receipt.json", report)
    assert not (vault / "receipt.json").exists()

    renamed_vault = tmp_path / "renamed-receipt-parent"
    vault.rename(renamed_vault)
    with pytest.raises(StaffTransportVaultPreflightError, match="scanned evidence vault"):
        write_preflight_receipt(renamed_vault / "receipt.json", report)
    assert not (renamed_vault / "receipt.json").exists()

    with backup.open("ab") as destination:
        destination.write(b"tampered")
    backup.chmod(0o600)
    with pytest.raises(StaffTransportVaultPreflightError, match="SHA-256 mismatch"):
        preflight_staff_transport_vault(backup, manifest, vault)
