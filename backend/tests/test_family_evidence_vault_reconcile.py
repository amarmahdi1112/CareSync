"""Report-only reconciliation gates for the private family-evidence vault."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest

import scripts.backup_database as backup_module
import scripts.family_evidence_vault_reconcile as reconcile_module
from scripts.family_evidence_vault_reconcile import (
    MINIMUM_PURGE_AGE_HOURS,
    PURGE_CONFIRMATION,
    EvidenceVaultReconcileError,
    reconcile_evidence_vault,
    write_reconcile_report,
)
from tests.test_family_evidence_vault_bundle import (
    CLEAN_ID,
    _create_database_backup,
    _create_vault,
    _reference,
)

ORPHAN_ID = UUID("77777777-7777-4777-8777-777777777777")


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


def test_report_matches_verified_inventory_without_mutating_vault(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backup, manifest = _create_database_backup(tmp_path, monkeypatch)
    vault = _create_vault(tmp_path)
    before = {
        path.relative_to(vault).as_posix(): (path.read_bytes(), path.stat().st_ino)
        for path in vault.rglob("v1.*")
    }

    report = reconcile_evidence_vault(backup, manifest, vault)

    assert report["format"] == "caresync-family-evidence-vault-reconcile-v1"
    assert report["mode"] == "report"
    assert report["expectedCount"] == 4
    assert report["presentCount"] == 4
    assert report["missing"] == []
    assert report["mismatched"] == []
    assert report["unexpected"] == []
    assert report["unsafe"] == []
    assert report["purge"]["available"] is False
    assert report["purge"]["eligibleReferences"] == []
    assert report["purge"]["purgedReferences"] == []
    assert (
        "backup_contract_has_no_snapshot_established_boundary" in report["purge"]["blockedReasons"]
    )
    after = {
        path.relative_to(vault).as_posix(): (path.read_bytes(), path.stat().st_ino)
        for path in vault.rglob("v1.*")
    }
    assert after == before


def test_report_accepts_a2_signed_release_delegation_inventory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The shared backup fixture marks CLEAN_ID as signed_release_delegation.
    # Reconciliation must treat it as a canonical required object, not an
    # unsupported or unexpected A1-era artifact.
    backup, manifest = _create_database_backup(tmp_path, monkeypatch)
    report = reconcile_evidence_vault(backup, manifest, _create_vault(tmp_path))
    assert report["expectedCount"] == 4
    assert report["presentCount"] == 4
    assert report["missing"] == []
    assert report["mismatched"] == []


def test_report_finds_missing_unexpected_and_symlink_without_following_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backup, manifest = _create_database_backup(tmp_path, monkeypatch)
    vault = _create_vault(tmp_path)
    vault.joinpath(*_reference(CLEAN_ID).split("/")).unlink()
    orphan_reference = _reference(ORPHAN_ID)
    orphan = _write_private(vault, orphan_reference, b"%PDF-1.7 orphan\n")
    outside = tmp_path / "outside"
    outside.mkdir(mode=0o700)
    sentinel = outside / "sentinel.pdf"
    sentinel.write_bytes(b"outside must remain untouched")
    sentinel.chmod(0o600)
    (vault / "linked-outside").symlink_to(outside, target_is_directory=True)

    report = reconcile_evidence_vault(backup, manifest, vault)

    assert report["missing"] == [_reference(CLEAN_ID)]
    assert [item["reference"] for item in report["unexpected"]] == [orphan_reference]
    assert report["unexpected"][0]["canonical"] is True
    assert report["unexpected"][0]["purgeEligible"] is False
    assert report["unexpected"][0]["measurement"] == {
        "device": orphan.stat().st_dev,
        "inode": orphan.stat().st_ino,
        "mode": "0600",
        "linkCount": 1,
        "byteSize": len(b"%PDF-1.7 orphan\n"),
        "modifiedNs": orphan.stat().st_mtime_ns,
        "changedNs": orphan.stat().st_ctime_ns,
        "contentSha256": hashlib.sha256(b"%PDF-1.7 orphan\n").hexdigest(),
    }
    assert {item["reason"] for item in report["unsafe"]} >= {"symbolic_link"}
    assert orphan.exists()
    assert sentinel.read_bytes() == b"outside must remain untouched"


def test_expected_hardlink_is_corrupt_and_never_authorizes_purge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backup, manifest = _create_database_backup(tmp_path, monkeypatch)
    vault = _create_vault(tmp_path)
    clean = vault.joinpath(*_reference(CLEAN_ID).split("/"))
    alias = clean.with_name("alias.pdf")
    os.link(clean, alias)

    report = reconcile_evidence_vault(backup, manifest, vault)

    assert report["mismatched"] == [
        {"reference": _reference(CLEAN_ID), "reason": "unsafe_or_unreadable"}
    ]
    assert "file_link_count_not_one" in {item["reason"] for item in report["unsafe"]}
    assert report["purge"]["eligibleReferences"] == []
    assert clean.exists() and alias.exists()


def test_oversized_expected_object_is_a_mismatch_without_unbounded_hashing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backup, manifest = _create_database_backup(tmp_path, monkeypatch)
    vault = _create_vault(tmp_path)
    clean = vault.joinpath(*_reference(CLEAN_ID).split("/"))
    with clean.open("ab") as destination:
        destination.write(b"unexpected extra bytes")

    report = reconcile_evidence_vault(backup, manifest, vault)

    assert {
        "reference": _reference(CLEAN_ID),
        "reason": "byte_size_mismatch",
    } in report["mismatched"]
    assert not any(item["reference"] == _reference(CLEAN_ID) for item in report["indeterminate"])
    assert "expected_objects_mismatched" in report["purge"]["blockedReasons"]


def test_purge_requests_always_fail_closed_and_leave_historical_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_now = datetime.now(UTC)
    backup_time = real_now + timedelta(days=40)

    class FutureDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            value = backup_time
            return value if tz is not None else value.replace(tzinfo=None)

    monkeypatch.setattr(backup_module, "datetime", FutureDatetime)
    backup, manifest = _create_database_backup(tmp_path, monkeypatch)
    vault = _create_vault(tmp_path)
    orphan_reference = _reference(ORPHAN_ID)
    orphan = _write_private(vault, orphan_reference, b"%PDF-1.7 settled orphan\n")
    observed_now = real_now + timedelta(days=80)

    report = reconcile_evidence_vault(
        backup,
        manifest,
        vault,
        now=observed_now,
    )
    item = next(value for value in report["unexpected"] if value["reference"] == orphan_reference)
    assert item["historicalCandidate"] is True
    assert item["purgeEligible"] is False
    assert report["purge"]["historicalCandidateReferences"] == [orphan_reference]

    with pytest.raises(EvidenceVaultReconcileError, match="exact confirmation"):
        reconcile_evidence_vault(
            backup,
            manifest,
            vault,
            purge=True,
            confirmation="yes",
            now=observed_now,
        )
    assert orphan.exists()

    with pytest.raises(EvidenceVaultReconcileError, match="report-only"):
        reconcile_evidence_vault(
            backup,
            manifest,
            vault,
            purge=True,
            confirmation=PURGE_CONFIRMATION,
            now=observed_now,
        )
    assert orphan.read_bytes() == b"%PDF-1.7 settled orphan\n"


def test_age_floor_cannot_be_weakened(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backup, manifest = _create_database_backup(tmp_path, monkeypatch)
    vault = _create_vault(tmp_path)

    with pytest.raises(EvidenceVaultReconcileError, match="cannot be below"):
        reconcile_evidence_vault(
            backup,
            manifest,
            vault,
            minimum_age_hours=MINIMUM_PURGE_AGE_HOURS - 1,
        )


def test_absent_or_symlinked_root_and_tampered_backup_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backup, manifest = _create_database_backup(tmp_path, monkeypatch)
    absent = tmp_path / "absent-vault"
    report = reconcile_evidence_vault(backup, manifest, absent)
    assert report["presentCount"] == 0
    assert len(report["missing"]) == 4
    assert report["unsafe"] == [{"reference": ".", "reason": "vault_root_absent"}]
    assert not absent.exists()

    real_root = _create_vault(tmp_path)
    linked_root = tmp_path / "linked-vault"
    linked_root.symlink_to(real_root, target_is_directory=True)
    with pytest.raises(EvidenceVaultReconcileError, match="symbolic-link component"):
        reconcile_evidence_vault(backup, manifest, linked_root)

    with backup.open("ab") as destination:
        destination.write(b"tampered")
    backup.chmod(0o600)
    with pytest.raises(EvidenceVaultReconcileError, match="SHA-256 mismatch"):
        reconcile_evidence_vault(backup, manifest, real_root)


def test_noncanonical_unexpected_file_is_reported_and_never_eligible(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backup, manifest = _create_database_backup(tmp_path, monkeypatch)
    vault = _create_vault(tmp_path)
    unexpected = vault / "manual-note.txt"
    unexpected.write_text("not an object", encoding="utf-8")
    unexpected.chmod(0o600)

    report = reconcile_evidence_vault(backup, manifest, vault)

    item = next(value for value in report["unexpected"] if value["reference"] == unexpected.name)
    assert item["canonical"] is False
    assert item["historicalCandidate"] is False
    assert item["purgeEligible"] is False
    assert "noncanonical_reference" in item["reasons"]
    assert "noncanonical_unexpected_files_present" in report["purge"]["blockedReasons"]
    assert unexpected.exists()


def test_unexpected_file_change_while_hashing_is_indeterminate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backup, manifest = _create_database_backup(tmp_path, monkeypatch)
    vault = _create_vault(tmp_path)
    orphan_reference = _reference(ORPHAN_ID)
    orphan = _write_private(vault, orphan_reference, b"%PDF-1.7 changing\n")
    target_identity = (orphan.stat().st_dev, orphan.stat().st_ino)
    original_read = os.read
    changed = False

    def racing_read(descriptor: int, amount: int) -> bytes:
        nonlocal changed
        chunk = original_read(descriptor, amount)
        details = os.fstat(descriptor)
        if chunk and not changed and (details.st_dev, details.st_ino) == target_identity:
            changed = True
            with orphan.open("ab") as destination:
                destination.write(b"concurrent")
        return chunk

    monkeypatch.setattr(reconcile_module.os, "read", racing_read)

    report = reconcile_evidence_vault(backup, manifest, vault)

    item = next(value for value in report["unexpected"] if value["reference"] == orphan_reference)
    assert changed is True
    assert item["classification"] == "indeterminate"
    assert item["measurement"] is None
    assert item["historicalCandidate"] is False
    assert item["purgeEligible"] is False
    assert "concurrent_file_change" in item["reasons"]
    assert {
        "reference": orphan_reference,
        "reason": "concurrent_file_change",
    } in report["indeterminate"]
    assert "indeterminate_vault_state" in report["purge"]["blockedReasons"]


def test_private_report_output_is_no_clobber_and_symlink_safe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backup, manifest = _create_database_backup(tmp_path, monkeypatch)
    vault = _create_vault(tmp_path)
    report = reconcile_evidence_vault(backup, manifest, vault)
    output_directory = tmp_path / "reports"
    output_directory.mkdir(mode=0o700)
    output = output_directory / "reconcile.json"

    write_reconcile_report(output, report)

    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert json.loads(output.read_text(encoding="utf-8")) == report
    with pytest.raises(EvidenceVaultReconcileError, match="Refusing to replace"):
        write_reconcile_report(output, report)
    assert json.loads(output.read_text(encoding="utf-8")) == report

    linked_output_directory = tmp_path / "linked-reports"
    linked_output_directory.symlink_to(output_directory, target_is_directory=True)
    with pytest.raises(EvidenceVaultReconcileError, match="symbolic-link component"):
        write_reconcile_report(linked_output_directory / "second.json", report)
    assert not (output_directory / "second.json").exists()


def test_naive_reconciliation_time_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backup, manifest = _create_database_backup(tmp_path, monkeypatch)
    vault = _create_vault(tmp_path)

    with pytest.raises(EvidenceVaultReconcileError, match="must include a timezone"):
        reconcile_evidence_vault(
            backup,
            manifest,
            vault,
            now=datetime(2026, 7, 17),
        )
