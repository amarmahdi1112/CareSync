"""Portable contract tests for the bounded 0029D joint recovery certifier."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import tempfile
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import scripts.family_authority_joint_recovery_certification as certification
from scripts.family_authority_joint_recovery_certification import (
    DISPOSABLE_DATA_DIRECTORY_PREFIX,
    DISPOSABLE_MARKER_FORMAT,
    DISPOSABLE_MARKER_NAME,
    REQUIRED_REVISION,
    JointRecoveryCertificationError,
    _validate_disposable_data_directory,
    certify_joint_recovery,
    joint_disposable_confirmation,
)
from scripts.family_evidence_vault_bundle import EvidenceVaultBundleError
from scripts.restore_database import write_private_restore_receipt

ARTIFACT_BYTES = {
    "database.json.gz": b"backup",
    "database.manifest.json": b"manifest",
    "evidence.zip": b"bundle",
    "evidence.manifest.json": b"bundle-manifest",
}


def _private_file(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    path.write_bytes(content)
    path.chmod(0o600)


def _seed_artifacts(root: Path) -> tuple[Path, Path, Path, Path]:
    paths = tuple(root / name for name in ARTIFACT_BYTES)
    for path in paths:
        _private_file(path, ARTIFACT_BYTES[path.name])
    return paths  # type: ignore[return-value]


def _target_directory(system_identifier: str) -> Path:
    scratch_root = Path("/private/tmp") if Path("/private/tmp").is_dir() else Path("/tmp")
    target = Path(
        tempfile.mkdtemp(prefix=DISPOSABLE_DATA_DIRECTORY_PREFIX, dir=scratch_root)
    )
    target.chmod(0o700)
    _private_file(target / "PG_VERSION", b"17\n")
    _private_file(target / "postmaster.pid", b"123\n")
    marker = {
        "format": DISPOSABLE_MARKER_FORMAT,
        "purpose": "0029D-artifact-recovery-consistency",
        "databaseName": "caresync",
        "systemIdentifier": system_identifier,
    }
    _private_file(
        target / DISPOSABLE_MARKER_NAME,
        (json.dumps(marker, sort_keys=True) + "\n").encode("utf-8"),
    )
    return target


@pytest.fixture
def disposable_target() -> tuple[Path, str]:
    system_identifier = "7612345678901234567"
    target = _target_directory(system_identifier)
    try:
        yield target, system_identifier
    finally:
        shutil.rmtree(target, ignore_errors=True)


def _inventory() -> list[dict[str, Any]]:
    return [
        {
            "objectId": "33333333-3333-4333-8333-333333333333",
            "organizationId": "11111111-1111-4111-8111-111111111111",
            "familyId": "22222222-2222-4222-8222-222222222222",
            "evidenceKind": "court_order",
            "objectVersion": 1,
            "storageReference": (
                "11111111111141118111111111111111/"
                "22222222222242228222222222222222/"
                "33333333333343338333333333333333/v1.pdf"
            ),
            "mediaType": "application/pdf",
            "byteSize": 12,
            "contentSha256": "a" * 64,
            "lifecycleStatus": "quarantined",
            "assessmentVersion": 1,
            "assessmentDecision": "quarantined",
            "terminalReasonCode": None,
            "disposition": "included",
        }
    ]


def _artifacts() -> tuple[dict[str, Any], dict[str, Any]]:
    inventory = _inventory()
    inventory_digest = hashlib.sha256(
        json.dumps(inventory, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()
    counts = {
        "alembic_version": 1,
        "family_authority_evidence_object_assessments": 1,
        "family_authority_evidence_objects": 1,
    }
    backup = {
        "header": {
            "databaseType": "postgres",
            "alembicRevisions": [REQUIRED_REVISION],
            "tables": sorted(counts),
        },
        "manifest": {
            "sha256Compressed": hashlib.sha256(ARTIFACT_BYTES["database.json.gz"]).hexdigest(),
            "sha256Rows": "c" * 64,
            "tableCounts": counts,
            "totalRows": sum(counts.values()),
        },
        "tableCounts": counts,
    }
    evidence = {
        "manifest": {
            "sha256Bundle": hashlib.sha256(ARTIFACT_BYTES["evidence.zip"]).hexdigest(),
            "inventorySha256": inventory_digest,
            "databaseBackup": {
                "backup": "database.json.gz",
                "manifest": "database.manifest.json",
                "sha256Compressed": hashlib.sha256(
                    ARTIFACT_BYTES["database.json.gz"]
                ).hexdigest(),
                "sha256Manifest": hashlib.sha256(
                    ARTIFACT_BYTES["database.manifest.json"]
                ).hexdigest(),
                "sha256Rows": "c" * 64,
                "alembicRevisions": [REQUIRED_REVISION],
            },
        },
        "objects": inventory,
        "objectCount": 1,
        "includedObjectCount": 1,
        "rejectedObjectCount": 0,
    }
    return backup, evidence


def _observation(
    target: Path,
    system_identifier: str,
    *,
    counts: dict[str, int],
    inventory: list[dict[str, Any]] | None,
    sha256_rows: str,
) -> dict[str, Any]:
    return {
        "databaseName": "caresync",
        "serverAddress": "127.0.0.1",
        "serverPort": 55479,
        "dataDirectory": os.fspath(target),
        "systemIdentifier": system_identifier,
        "postmasterStartedAt": "2026-07-22T00:00:00+00:00",
        "otherClientSessions": 0,
        "tableCounts": counts,
        "applicationRows": sum(
            value for key, value in counts.items() if key != "alembic_version"
        ),
        "inventory": inventory,
        "sha256Rows": sha256_rows,
    }


def _happy_case(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    disposable_target: tuple[Path, str],
    *,
    mutate_preflight: Callable[[dict[str, Any]], None] | None = None,
    mutate_postflight: Callable[[dict[str, Any]], None] | None = None,
    expand_database_receipt: bool = False,
    boolean_database_total_rows: bool = False,
    vault_failure: bool = False,
) -> dict[str, Any]:
    target, system_identifier = disposable_target
    artifacts = _seed_artifacts(tmp_path / "artifacts")
    backup_path, manifest_path, bundle_path, _ = artifacts
    backup, evidence = _artifacts()
    empty_counts = {
        key: (1 if key == "alembic_version" else 0)
        for key in backup["manifest"]["tableCounts"]
    }
    preflight = _observation(
        target,
        system_identifier,
        counts=empty_counts,
        inventory=None,
        sha256_rows="e" * 64,
    )
    postflight = _observation(
        target,
        system_identifier,
        counts=backup["manifest"]["tableCounts"],
        inventory=evidence["objects"],
        sha256_rows=backup["manifest"]["sha256Rows"],
    )
    if mutate_preflight is not None:
        mutate_preflight(preflight)
    if mutate_postflight is not None:
        mutate_postflight(postflight)
    observations = iter([preflight, postflight])
    configured = SimpleNamespace(
        database_type="postgres",
        database_host="127.0.0.1",
        database_port=55479,
        database_name="caresync",
        database_user="postgres",
    )
    database_receipt = tmp_path / "receipts" / "database.json"
    vault_receipt = tmp_path / "receipts" / "vault.json"
    joint_receipt = tmp_path / "receipts" / "joint.json"
    vault_destination = tmp_path / "restore" / "vault"
    restore_calls: list[dict[str, Any]] = []

    monkeypatch.setattr(certification, "verify_backup_artifacts", lambda *_: backup)
    monkeypatch.setattr(certification, "verify_evidence_bundle", lambda *_: evidence)
    monkeypatch.setattr(certification, "_observe_target", lambda *_, **__: next(observations))

    def fake_database_restore(*_: Any, **kwargs: Any) -> dict[str, Any]:
        restore_calls.append(kwargs)
        result = {
            "format": "caresync-restore-verification-v1",
            "verifiedAt": "2026-07-22T00:00:01+00:00",
            "backup": backup_path.name,
            "backupSha256": backup["manifest"]["sha256Compressed"],
            "target": "127.0.0.1:55479/caresync",
            "alembicRevisions": [REQUIRED_REVISION],
            "tableCounts": backup["manifest"]["tableCounts"],
            "totalRows": backup["manifest"]["totalRows"],
            "sha256Rows": backup["manifest"]["sha256Rows"],
            "strongTargetAttestation": {
                "performed": True,
                "targetWasEmpty": True,
                "otherClientSessions": 0,
            },
        }
        receipt_result = result
        if expand_database_receipt:
            result["unexpected"] = "expanded-shape"
        elif boolean_database_total_rows:
            receipt_result = {**result, "totalRows": True}
        write_private_restore_receipt(kwargs["receipt_path"], receipt_result)
        return result

    def fake_vault_restore(*args: Any, **kwargs: Any) -> dict[str, Any]:
        destination = args[4]
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        destination.parent.chmod(0o700)
        destination.mkdir(mode=0o700)
        if vault_failure:
            raise EvidenceVaultBundleError("synthetic partial vault failure")
        result = {
            "format": "caresync-family-evidence-vault-restore-v1",
            "verifiedAt": "2026-07-22T00:00:02+00:00",
            "databaseBackup": evidence["manifest"]["databaseBackup"],
            "bundle": bundle_path.name,
            "bundleSha256": evidence["manifest"]["sha256Bundle"],
            "inventorySha256": evidence["manifest"]["inventorySha256"],
            "objectCount": 1,
            "restoredObjectCount": 1,
            "rejectedObjectCount": 0,
        }
        write_private_restore_receipt(kwargs["receipt_path"], result)
        return result

    monkeypatch.setattr(certification, "restore_and_verify", fake_database_restore)
    monkeypatch.setattr(certification, "restore_evidence_bundle", fake_vault_restore)
    monkeypatch.setattr(
        certification,
        "reconcile_evidence_vault",
        lambda *_: {
            "expectedCount": 1,
            "presentCount": 1,
            "missing": [],
            "mismatched": [],
            "unexpected": [],
            "unsafe": [],
            "indeterminate": [],
            "unclassifiedDirectories": [],
        },
    )
    confirmation = joint_disposable_confirmation(
        configured,
        expected_data_directory=target,
        expected_system_identifier=system_identifier,
        backup_sha256=backup["manifest"]["sha256Compressed"],
        manifest_sha256=hashlib.sha256(ARTIFACT_BYTES["database.manifest.json"]).hexdigest(),
        bundle_sha256=evidence["manifest"]["sha256Bundle"],
        bundle_manifest_sha256=hashlib.sha256(
            ARTIFACT_BYTES["evidence.manifest.json"]
        ).hexdigest(),
    )
    return {
        "artifacts": artifacts,
        "kwargs": {
            "expected_data_directory": target,
            "expected_system_identifier": system_identifier,
            "vault_destination": vault_destination,
            "database_receipt": database_receipt,
            "vault_receipt": vault_receipt,
            "joint_receipt": joint_receipt,
            "confirmation": confirmation,
            "settings": configured,
        },
        "backup": backup,
        "evidence": evidence,
        "restoreCalls": restore_calls,
    }


def test_disposable_data_directory_requires_exact_private_marker(
    disposable_target: tuple[Path, str],
) -> None:
    target, system_identifier = disposable_target

    assert _validate_disposable_data_directory(
        target,
        expected_system_identifier=system_identifier,
        database_name="caresync",
    ) == target

    marker = target / DISPOSABLE_MARKER_NAME
    value = json.loads(marker.read_text(encoding="utf-8"))
    value["systemIdentifier"] = "7000000000000000000"
    marker.write_text(json.dumps(value), encoding="utf-8")
    marker.chmod(0o600)
    with pytest.raises(JointRecoveryCertificationError, match="marker does not identify"):
        _validate_disposable_data_directory(
            target,
            expected_system_identifier=system_identifier,
            database_name="caresync",
        )


def test_disposable_data_directory_rejects_non_scratch_location(tmp_path: Path) -> None:
    system_identifier = "7612345678901234567"
    target = tmp_path / f"{DISPOSABLE_DATA_DIRECTORY_PREFIX}wrong-root"
    target.mkdir(mode=0o700)
    target.chmod(0o700)
    _private_file(target / "PG_VERSION", b"17\n")
    _private_file(target / "postmaster.pid", b"123\n")
    _private_file(
        target / DISPOSABLE_MARKER_NAME,
        json.dumps(
            {
                "format": DISPOSABLE_MARKER_FORMAT,
                "purpose": "0029D-artifact-recovery-consistency",
                "databaseName": "caresync",
                "systemIdentifier": system_identifier,
            }
        ).encode("utf-8"),
    )

    with pytest.raises(JointRecoveryCertificationError, match="scratch cluster"):
        _validate_disposable_data_directory(
            target,
            expected_system_identifier=system_identifier,
            database_name="caresync",
        )


def test_joint_confirmation_discloses_no_target_identity(tmp_path: Path) -> None:
    settings = SimpleNamespace(
        database_host="127.0.0.1",
        database_port=55479,
        database_name="caresync",
    )
    system_identifier = "7612345678901234567"
    token = joint_disposable_confirmation(
        settings,
        expected_data_directory=tmp_path / "private-target",
        expected_system_identifier=system_identifier,
        backup_sha256="b" * 64,
        manifest_sha256="c" * 64,
        bundle_sha256="d" * 64,
        bundle_manifest_sha256="e" * 64,
    )

    assert token.startswith("CONFIRM-CARESYNC-0029D-JOINT-RECOVERY:")
    assert system_identifier not in token
    assert os.fspath(tmp_path) not in token
    assert "55479" not in token


def test_joint_certifier_closes_only_artifact_recovery_consistency(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    disposable_target: tuple[Path, str],
) -> None:
    target, system_identifier = disposable_target
    backup_path, manifest_path, bundle_path, bundle_manifest_path = _seed_artifacts(
        tmp_path / "artifacts"
    )

    database_receipt = tmp_path / "receipts" / "database.json"
    vault_receipt = tmp_path / "receipts" / "vault.json"
    joint_receipt = tmp_path / "receipts" / "joint.json"
    vault_destination = tmp_path / "restore" / "vault"
    configured = SimpleNamespace(
        database_type="postgres",
        database_host="127.0.0.1",
        database_port=55479,
        database_name="caresync",
        database_user="postgres",
    )
    backup, evidence = _artifacts()
    empty_counts = {
        key: (1 if key == "alembic_version" else 0)
        for key in backup["manifest"]["tableCounts"]
    }
    observations = iter(
        [
            _observation(
                target,
                system_identifier,
                counts=empty_counts,
                inventory=None,
                sha256_rows="e" * 64,
            ),
            _observation(
                target,
                system_identifier,
                counts=backup["manifest"]["tableCounts"],
                inventory=evidence["objects"],
                sha256_rows=backup["manifest"]["sha256Rows"],
            ),
        ]
    )
    restore_arguments: dict[str, Any] = {}

    monkeypatch.setattr(certification, "verify_backup_artifacts", lambda *_: backup)
    monkeypatch.setattr(certification, "verify_evidence_bundle", lambda *_: evidence)
    monkeypatch.setattr(certification, "_observe_target", lambda *_, **__: next(observations))

    def fake_database_restore(*_: Any, **kwargs: Any) -> dict[str, Any]:
        restore_arguments.update(kwargs)
        result = {
            "format": "caresync-restore-verification-v1",
            "verifiedAt": "2026-07-22T00:00:01+00:00",
            "backup": backup_path.name,
            "backupSha256": backup["manifest"]["sha256Compressed"],
            "target": "127.0.0.1:55479/caresync",
            "alembicRevisions": [REQUIRED_REVISION],
            "tableCounts": backup["manifest"]["tableCounts"],
            "totalRows": backup["manifest"]["totalRows"],
            "sha256Rows": backup["manifest"]["sha256Rows"],
            "strongTargetAttestation": {
                "performed": True,
                "targetWasEmpty": True,
                "otherClientSessions": 0,
            },
        }
        write_private_restore_receipt(kwargs["receipt_path"], result)
        return result

    def fake_vault_restore(*args: Any, **kwargs: Any) -> dict[str, Any]:
        destination = args[4]
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        destination.parent.chmod(0o700)
        destination.mkdir(mode=0o700)
        result = {
            "format": "caresync-family-evidence-vault-restore-v1",
            "verifiedAt": "2026-07-22T00:00:02+00:00",
            "databaseBackup": evidence["manifest"]["databaseBackup"],
            "bundle": bundle_path.name,
            "bundleSha256": evidence["manifest"]["sha256Bundle"],
            "inventorySha256": evidence["manifest"]["inventorySha256"],
            "objectCount": 1,
            "restoredObjectCount": 1,
            "rejectedObjectCount": 0,
        }
        write_private_restore_receipt(kwargs["receipt_path"], result)
        return result

    monkeypatch.setattr(certification, "restore_and_verify", fake_database_restore)
    monkeypatch.setattr(certification, "restore_evidence_bundle", fake_vault_restore)
    monkeypatch.setattr(
        certification,
        "reconcile_evidence_vault",
        lambda *_: {
            "expectedCount": 1,
            "presentCount": 1,
            "missing": [],
            "mismatched": [],
            "unexpected": [],
            "unsafe": [],
            "indeterminate": [],
            "unclassifiedDirectories": [],
        },
    )
    confirmation = joint_disposable_confirmation(
        configured,
        expected_data_directory=target,
        expected_system_identifier=system_identifier,
        backup_sha256=backup["manifest"]["sha256Compressed"],
        manifest_sha256=hashlib.sha256(ARTIFACT_BYTES["database.manifest.json"]).hexdigest(),
        bundle_sha256=evidence["manifest"]["sha256Bundle"],
        bundle_manifest_sha256=hashlib.sha256(
            ARTIFACT_BYTES["evidence.manifest.json"]
        ).hexdigest(),
    )

    result = certify_joint_recovery(
        backup_path,
        manifest_path,
        bundle_path,
        bundle_manifest_path,
        expected_data_directory=target,
        expected_system_identifier=system_identifier,
        vault_destination=vault_destination,
        database_receipt=database_receipt,
        vault_receipt=vault_receipt,
        joint_receipt=joint_receipt,
        confirmation=confirmation,
        settings=configured,
    )

    assert restore_arguments["prepare_empty_target"] is False
    assert restore_arguments["require_empty_target"] is True
    assert restore_arguments["expected_data_directory"] == target
    assert restore_arguments["expected_system_identifier"] == system_identifier
    assert restore_arguments["configured_settings"] is configured
    assert result["scope"] == {
        "artifactRecoveryConsistencyOnly": True,
        "recoveryConsistencyProven": True,
        "sourceWriterQuiescenceProven": False,
        "authoritativeSourceCompletenessProven": False,
        "authoritativeSameSnapshotCaptureProven": False,
        "sourceVaultUnexpectedEntriesRuledOut": False,
        "targetSchemaAuthenticityProven": False,
        "cutoverAuthority": False,
        "releaseAuthority": False,
        "purgeAuthority": False,
        "migrationInvoked": False,
    }
    assert stat.S_IMODE(joint_receipt.stat().st_mode) == 0o600
    assert joint_receipt.stat().st_nlink == 1
    serialized = joint_receipt.read_text(encoding="utf-8")
    assert system_identifier not in serialized
    assert os.fspath(target) not in serialized
    assert evidence["objects"][0]["objectId"] not in serialized


def test_joint_certifier_rejects_non_0029d_before_target_or_restore(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backup, evidence = _artifacts()
    backup["header"]["alembicRevisions"] = ["0030_staff_screening_paths"]
    monkeypatch.setattr(certification, "verify_backup_artifacts", lambda *_: backup)
    monkeypatch.setattr(certification, "verify_evidence_bundle", lambda *_: evidence)
    monkeypatch.setattr(
        certification,
        "_observe_target",
        lambda *_, **__: pytest.fail("target must not be observed"),
    )
    monkeypatch.setattr(
        certification,
        "restore_and_verify",
        lambda *_, **__: pytest.fail("restore must not run"),
    )
    configured = SimpleNamespace(
        database_type="postgres",
        database_host="127.0.0.1",
        database_port=55479,
        database_name="caresync",
        database_user="postgres",
    )
    artifact_paths = _seed_artifacts(tmp_path / "artifacts")

    with pytest.raises(JointRecoveryCertificationError, match="exact revision"):
        certify_joint_recovery(
            *artifact_paths,
            expected_data_directory=tmp_path / "unused",
            expected_system_identifier="7612345678901234567",
            vault_destination=tmp_path / "vault",
            database_receipt=tmp_path / "db.json",
            vault_receipt=tmp_path / "vault.json",
            joint_receipt=tmp_path / "joint.json",
            confirmation="unused",
            settings=configured,
        )


def test_unsafe_output_parent_blocks_before_database_restore(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    disposable_target: tuple[Path, str],
) -> None:
    target, system_identifier = disposable_target
    artifact_paths = _seed_artifacts(tmp_path / "artifacts")
    backup, evidence = _artifacts()
    monkeypatch.setattr(certification, "verify_backup_artifacts", lambda *_: backup)
    monkeypatch.setattr(certification, "verify_evidence_bundle", lambda *_: evidence)
    monkeypatch.setattr(
        certification,
        "restore_and_verify",
        lambda *_, **__: pytest.fail("database restore must not run"),
    )
    unsafe_parent = tmp_path / "unsafe-receipts"
    unsafe_parent.mkdir(mode=0o755)
    unsafe_parent.chmod(0o755)
    configured = SimpleNamespace(
        database_type="postgres",
        database_host="127.0.0.1",
        database_port=55479,
        database_name="caresync",
        database_user="postgres",
    )

    with pytest.raises(JointRecoveryCertificationError, match="mode 0700"):
        certify_joint_recovery(
            *artifact_paths,
            expected_data_directory=target,
            expected_system_identifier=system_identifier,
            vault_destination=tmp_path / "safe-vault-parent" / "vault",
            database_receipt=unsafe_parent / "database.json",
            vault_receipt=tmp_path / "safe-receipts" / "vault.json",
            joint_receipt=tmp_path / "safe-receipts" / "joint.json",
            confirmation="not-reached",
            settings=configured,
        )


@pytest.mark.parametrize("mutation", ["hardlink", "symlink", "wrong-mode"])
def test_unsafe_artifact_identity_blocks_before_verification_or_restore(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    artifacts = list(_seed_artifacts(tmp_path / "artifacts"))
    if mutation == "hardlink":
        artifacts[1].unlink()
        os.link(artifacts[0], artifacts[1])
    elif mutation == "symlink":
        artifacts[2].unlink()
        artifacts[2].symlink_to(artifacts[0])
    else:
        artifacts[3].chmod(0o644)
    monkeypatch.setattr(
        certification,
        "verify_backup_artifacts",
        lambda *_: pytest.fail("unsafe artifacts must not be verified"),
    )
    monkeypatch.setattr(
        certification,
        "restore_and_verify",
        lambda *_, **__: pytest.fail("unsafe artifacts must not be restored"),
    )
    configured = SimpleNamespace(
        database_type="postgres",
        database_host="127.0.0.1",
        database_port=55479,
        database_name="caresync",
        database_user="postgres",
    )
    joint_receipt = tmp_path / "joint.json"

    with pytest.raises(
        JointRecoveryCertificationError,
        match="symbolic link|mode 0600 single-link",
    ):
        certify_joint_recovery(
            *artifacts,
            expected_data_directory=tmp_path / "unused-pgdata",
            expected_system_identifier="7612345678901234567",
            vault_destination=tmp_path / "vault",
            database_receipt=tmp_path / "db.json",
            vault_receipt=tmp_path / "vault.json",
            joint_receipt=joint_receipt,
            confirmation="unused",
            settings=configured,
        )
    assert not joint_receipt.exists()


def test_dot_traversal_symlink_spelling_cannot_escape_into_pgdata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    disposable_target: tuple[Path, str],
) -> None:
    target, system_identifier = disposable_target
    artifacts = _seed_artifacts(tmp_path / "artifacts")
    link = tmp_path / "pgdata-link"
    link.symlink_to(target, target_is_directory=True)
    disguised_destination = link / ".." / target.name / "vault"
    monkeypatch.setattr(
        certification,
        "restore_and_verify",
        lambda *_, **__: pytest.fail("traversal path must not reach restore"),
    )

    with pytest.raises(JointRecoveryCertificationError, match="dot traversal"):
        certify_joint_recovery(
            *artifacts,
            expected_data_directory=target,
            expected_system_identifier=system_identifier,
            vault_destination=disguised_destination,
            database_receipt=tmp_path / "receipts" / "db.json",
            vault_receipt=tmp_path / "receipts" / "vault.json",
            joint_receipt=tmp_path / "receipts" / "joint.json",
            confirmation="unused",
        )
    assert not (target / "vault").exists()


@pytest.mark.parametrize("existing", ["joint-receipt", "vault-destination"])
def test_existing_recovery_output_blocks_without_clobber_or_database_restore(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    disposable_target: tuple[Path, str],
    existing: str,
) -> None:
    case = _happy_case(tmp_path, monkeypatch, disposable_target)
    kwargs = case["kwargs"]
    if existing == "joint-receipt":
        _private_file(kwargs["joint_receipt"], b"winner")
    else:
        kwargs["vault_destination"].parent.mkdir(parents=True, mode=0o700)
        kwargs["vault_destination"].parent.chmod(0o700)
        kwargs["vault_destination"].mkdir(mode=0o700)

    with pytest.raises(JointRecoveryCertificationError, match="already exists"):
        certify_joint_recovery(*case["artifacts"], **kwargs)
    assert case["restoreCalls"] == []
    if existing == "joint-receipt":
        assert kwargs["joint_receipt"].read_bytes() == b"winner"


@pytest.mark.parametrize("failure", ["confirmation", "system-identifier"])
def test_wrong_confirmation_or_cluster_identity_blocks_before_restore(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    disposable_target: tuple[Path, str],
    failure: str,
) -> None:
    case = _happy_case(tmp_path, monkeypatch, disposable_target)
    kwargs = case["kwargs"]
    expected = "confirmation" if failure == "confirmation" else "marker does not identify"
    if failure == "confirmation":
        kwargs["confirmation"] = "wrong"
    else:
        kwargs["expected_system_identifier"] = "7000000000000000000"

    with pytest.raises(JointRecoveryCertificationError, match=expected):
        certify_joint_recovery(*case["artifacts"], **kwargs)
    assert case["restoreCalls"] == []
    assert not kwargs["joint_receipt"].exists()


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("applicationRows", 1, "not empty"),
        ("otherClientSessions", 1, "not quiescent"),
        ("serverPort", 55480, "port identity changed"),
    ],
)
def test_preflight_state_blocks_before_restore(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    disposable_target: tuple[Path, str],
    field: str,
    value: Any,
    message: str,
) -> None:
    case = _happy_case(
        tmp_path,
        monkeypatch,
        disposable_target,
        mutate_preflight=lambda observation: observation.__setitem__(field, value),
    )

    with pytest.raises(JointRecoveryCertificationError, match=message):
        certify_joint_recovery(*case["artifacts"], **case["kwargs"])
    assert case["restoreCalls"] == []
    assert not case["kwargs"]["joint_receipt"].exists()


@pytest.mark.parametrize("mismatch", ["row-digest", "inventory"])
def test_postflight_mismatch_retains_component_receipts_but_never_closes_joint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    disposable_target: tuple[Path, str],
    mismatch: str,
) -> None:
    def mutate(observation: dict[str, Any]) -> None:
        if mismatch == "row-digest":
            observation["sha256Rows"] = "0" * 64
        else:
            observation["inventory"] = []

    case = _happy_case(
        tmp_path,
        monkeypatch,
        disposable_target,
        mutate_postflight=mutate,
    )
    with pytest.raises(JointRecoveryCertificationError, match="row digest|inventory differs"):
        certify_joint_recovery(*case["artifacts"], **case["kwargs"])

    assert len(case["restoreCalls"]) == 1
    assert case["kwargs"]["database_receipt"].is_file()
    assert case["kwargs"]["vault_receipt"].is_file()
    assert not case["kwargs"]["joint_receipt"].exists()


def test_expanded_component_receipt_shape_never_closes_joint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    disposable_target: tuple[Path, str],
) -> None:
    case = _happy_case(
        tmp_path,
        monkeypatch,
        disposable_target,
        expand_database_receipt=True,
    )
    with pytest.raises(JointRecoveryCertificationError, match="closed-shape"):
        certify_joint_recovery(*case["artifacts"], **case["kwargs"])
    assert case["kwargs"]["database_receipt"].is_file()
    assert case["kwargs"]["vault_receipt"].is_file()
    assert not case["kwargs"]["joint_receipt"].exists()


def test_boolean_component_count_cannot_equal_integer_receipt_field(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    disposable_target: tuple[Path, str],
) -> None:
    case = _happy_case(
        tmp_path,
        monkeypatch,
        disposable_target,
        boolean_database_total_rows=True,
    )
    with pytest.raises(JointRecoveryCertificationError, match="closed-shape"):
        certify_joint_recovery(*case["artifacts"], **case["kwargs"])
    assert not case["kwargs"]["joint_receipt"].exists()


def test_partial_vault_failure_leaves_database_receipt_but_no_joint_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    disposable_target: tuple[Path, str],
) -> None:
    case = _happy_case(
        tmp_path,
        monkeypatch,
        disposable_target,
        vault_failure=True,
    )
    with pytest.raises(JointRecoveryCertificationError, match="partial vault failure"):
        certify_joint_recovery(*case["artifacts"], **case["kwargs"])
    assert case["kwargs"]["database_receipt"].is_file()
    assert not case["kwargs"]["vault_receipt"].exists()
    assert not case["kwargs"]["joint_receipt"].exists()


def test_raw_manifest_byte_change_after_restore_blocks_joint_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    disposable_target: tuple[Path, str],
) -> None:
    case = _happy_case(tmp_path, monkeypatch, disposable_target)
    original_restore = certification.restore_and_verify

    def mutate_manifest_after_restore(*args: Any, **kwargs: Any) -> dict[str, Any]:
        result = original_restore(*args, **kwargs)
        manifest = case["artifacts"][1]
        manifest.write_bytes(ARTIFACT_BYTES[manifest.name] + b"\n")
        manifest.chmod(0o600)
        return result

    monkeypatch.setattr(certification, "restore_and_verify", mutate_manifest_after_restore)
    with pytest.raises(JointRecoveryCertificationError, match="byte level"):
        certify_joint_recovery(*case["artifacts"], **case["kwargs"])
    assert not case["kwargs"]["joint_receipt"].exists()


def test_bundle_substitution_failure_occurs_before_any_restore(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    disposable_target: tuple[Path, str],
) -> None:
    case = _happy_case(tmp_path, monkeypatch, disposable_target)
    monkeypatch.setattr(
        certification,
        "verify_evidence_bundle",
        lambda *_: (_ for _ in ()).throw(
            EvidenceVaultBundleError("different database backup")
        ),
    )

    with pytest.raises(JointRecoveryCertificationError, match="different database backup"):
        certify_joint_recovery(*case["artifacts"], **case["kwargs"])
    assert case["restoreCalls"] == []
    assert not case["kwargs"]["joint_receipt"].exists()
