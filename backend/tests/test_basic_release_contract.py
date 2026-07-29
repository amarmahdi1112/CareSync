"""Focused tests for the two-phase 0039 -> 0043 release evidence contract."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

from scripts import basic_release_contract
from scripts.basic_release_contract import (
    CANDIDATE_RECEIPT_FORMAT,
    COMMIT_RECEIPT_FORMAT,
    INTERMEDIATE_REVISION,
    NEW_0041_TABLES,
    SOURCE_REVISION,
    TARGET_REVISION,
    ReleaseContractError,
    _validate_candidate_receipt,
    atomic_rename_no_replace,
    bind_private_artifact,
    certify_source_resume,
    create_candidate_receipt,
    create_clone_certificate,
    create_commit_receipt,
    create_finalization_receipt,
    create_physical_backup_inventory,
    create_physical_rehearsal_observation,
    create_physical_rehearsal_receipt,
    create_resume_authorization,
    durability_barrier_private_tree,
    durable_publish_private_file,
    durable_remove_private_file,
    durable_rename_private_fence_no_replace,
    ensure_private_directory,
    validate_artifact_names,
    verify_candidate_receipt,
    verify_commit_receipt,
    verify_finalization_receipt,
    verify_live_commit_state,
    verify_physical_backup_inventory,
    verify_physical_rehearsal_receipt,
    verify_resume_authorization,
    verify_source_candidate,
    write_private_json_no_clobber,
)


def _digest(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def test_postgres_identity_normalizes_inet_host_address() -> None:
    source = Path(basic_release_contract.__file__).read_text(encoding="utf-8")

    assert "COALESCE(host(inet_server_addr()),'local')" in source
    assert "COALESCE(inet_server_addr()::text,'local')" not in source


def test_release_revision_contract_names_the_interrupted_0042_boundary() -> None:
    assert SOURCE_REVISION == "0039_admissions_decision_spine"
    assert INTERMEDIATE_REVISION == "0042_billing_policy_recert"
    assert TARGET_REVISION == "0043_org_wide_room_presence"


def _identity(
    *,
    port: int,
    data_directory: str,
    system_identifier: str,
) -> dict[str, object]:
    return {
        "databaseName": "caresync",
        "roleName": "release_owner",
        "sessionUser": "release_owner",
        "serverAddress": "127.0.0.1",
        "serverPort": port,
        "serverVersion": "17.5 (Homebrew)",
        "serverVersionNum": 170005,
        "dataDirectory": data_directory,
        "systemIdentifier": system_identifier,
    }


def _business(*, include_release_tables: bool, family_digest: str | None = None):
    family = {
        "name": "families",
        "rowCount": 2,
        "sha256Rows": family_digest or _digest("family rows"),
    }
    tables = [family]
    if include_release_tables:
        empty_digest = hashlib.sha256().hexdigest()
        tables.extend(
            {
                "name": name,
                "rowCount": 0,
                "sha256Rows": empty_digest,
            }
            for name in NEW_0041_TABLES
        )
    tables.sort(key=lambda table: table["name"])
    return {
        "tables": tables,
        "totalRows": 2,
        # Empty tables contribute no row lines, so the complete row digest is
        # legitimately unchanged by the migration.
        "sha256Rows": _digest("complete business row stream"),
    }


def _snapshot(
    *,
    revision: str,
    identity: dict[str, object],
    business: dict[str, object] | None = None,
) -> dict[str, object]:
    target = revision == TARGET_REVISION
    return {
        "revision": revision,
        "identity": identity,
        "business": business or _business(include_release_tables=target),
        "new0041TableCounts": {name: 0 if target else None for name in NEW_0041_TABLES},
        "billingPolicyProfile": "A" if target else None,
        "runtimeCertificate": {
            "hook": "Database.assert_basic_runtime_identity",
            "status": "passed" if target else "not_required",
        },
    }


def _private_directory(tmp_path: Path) -> Path:
    directory = tmp_path / "private"
    directory.mkdir(mode=0o700)
    directory.chmod(0o700)
    return directory


def _private_bytes(directory: Path, name: str, payload: bytes) -> Path:
    path = directory / name
    path.write_bytes(payload)
    path.chmod(0o600)
    return path


def _private_json(directory: Path, name: str, payload: dict[str, object]) -> Path:
    path = directory / name
    write_private_json_no_clobber(path, payload)
    return path


def _release_fixture(tmp_path: Path) -> dict[str, object]:
    directory = _private_directory(tmp_path)
    source = _snapshot(
        revision=SOURCE_REVISION,
        identity=_identity(
            port=5434,
            data_directory="/private/source-pgdata",
            system_identifier="7662593396547771482",
        ),
    )
    candidate = _snapshot(
        revision=TARGET_REVISION,
        identity=_identity(
            port=56555,
            data_directory="/private/disposable-pgdata",
            system_identifier="candidate-system-2",
        ),
    )
    promoted = _snapshot(
        revision=TARGET_REVISION,
        identity=copy.deepcopy(source["identity"]),
        business=copy.deepcopy(candidate["business"]),
    )

    backup = _private_bytes(directory, "caresync.json.gz", b"verified backup bytes")
    backup_sha = hashlib.sha256(backup.read_bytes()).hexdigest()
    manifest = _private_json(
        directory,
        "caresync.manifest.json",
        {
            "format": "caresync-logical-backup-v2",
            "backup": backup.name,
            "sha256Compressed": backup_sha,
        },
    )
    candidate_identity = candidate["identity"]
    restore_receipt = _private_json(
        directory,
        "restore.receipt.json",
        {
            "format": "caresync-restore-verification-v1",
            "verifiedAt": "2026-07-26T12:00:00+00:00",
            "backup": backup.name,
            "backupSha256": backup_sha,
            "target": "127.0.0.1:56555/caresync",
            "alembicRevisions": [SOURCE_REVISION],
            "tableCounts": {"alembic_version": 1, "families": 2},
            "totalRows": 3,
            "sha256Rows": _digest("backup rows"),
            "strongTargetAttestation": {
                "performed": True,
                "targetWasEmpty": True,
                "roleName": candidate_identity["roleName"],
                "databaseName": candidate_identity["databaseName"],
                "serverAddress": candidate_identity["serverAddress"],
                "serverPort": candidate_identity["serverPort"],
                "dataDirectory": candidate_identity["dataDirectory"],
                "systemIdentifier": candidate_identity["systemIdentifier"],
                "otherClientSessions": 0,
                "alembicRevisions": [SOURCE_REVISION],
                "tableCounts": {
                    "alembic_version": 1,
                    "families": 0,
                },
            },
        },
    )
    physical_backup_manifest = _private_bytes(
        directory,
        "physical-backup-manifest.json",
        b'{"PostgreSQL-Backup-Manifest-Version":2}\n',
    )
    physical_backup_inventory = _private_json(
        directory,
        "physical-backup.inventory.json",
        {
            "format": "caresync-basic-physical-backup-inventory-v2",
            "devicePolicy": "single-device-no-mounts",
            "entries": [],
            "sha256Tree": hashlib.sha256(b"[]").hexdigest(),
        },
    )
    retained_identity = _private_bytes(
        directory,
        "retained-postgres.identity",
        (
            b"data_directory=/private/source-pgdata\n"
            b"system_identifier=7662593396547771482\n"
            b"port=5434\n"
            b"database=caresync\n"
        ),
    )
    rehearsed_source = _snapshot(
        revision=SOURCE_REVISION,
        identity=_identity(
            port=56556,
            data_directory="/private/physical-rehearsal-pgdata",
            system_identifier="7662593396547771482",
        ),
    )
    physical_rehearsal_observation = directory / "physical-rehearsal.observation.json"
    create_physical_rehearsal_observation(
        rehearsal_snapshot=rehearsed_source,
        physical_backup_manifest_path=physical_backup_manifest,
        physical_backup_inventory_path=physical_backup_inventory,
        retained_identity_path=retained_identity,
        observation_path=physical_rehearsal_observation,
        online_attestation={
            "endpoint": "127.0.0.1:56556",
            "isInRecovery": False,
            "writerRoleStates": {
                "caresync_basic_app": "nologin",
                "caresync_transport_evidence_ingest": "nologin",
            },
            "otherClientSessions": 0,
        },
    )
    physical_rehearsal_receipt = directory / "physical-rehearsal.receipt.json"
    create_physical_rehearsal_receipt(
        observation_path=physical_rehearsal_observation,
        physical_backup_manifest_path=physical_backup_manifest,
        physical_backup_inventory_path=physical_backup_inventory,
        retained_identity_path=retained_identity,
        offline_control={
            "clusterState": "shut down",
            "systemIdentifier": "7662593396547771482",
            "dataDirectory": "/private/physical-rehearsal-pgdata",
        },
        receipt_path=physical_rehearsal_receipt,
    )
    prepared_fence_context = _private_bytes(
        directory,
        "prepared-fence.context",
        (
            b"status=prepared\n"
            b"run_directory=/private/release\n"
            b"candidate_receipt=/private/release/candidate-receipt.json\n"
            b"app_prior_login=login\n"
            b"ingest_prior_login=login\n"
            b"source_revision=0039_admissions_decision_spine\n"
            b"target_revision=0043_org_wide_room_presence\n"
        ),
    )
    release_probe_credential = _private_bytes(
        directory,
        "controlled-health-probe.credential",
        b"test-only-probe-credential",
    )
    release_source_manifest = _private_bytes(
        directory,
        "release-source.manifest.json",
        b'{"format":"test-release-source"}\n',
    )
    artifacts = {
        "backup": backup,
        "backup_manifest": manifest,
        "database_restore_receipt": restore_receipt,
        "physical_backup_manifest": physical_backup_manifest,
        "physical_backup_inventory": physical_backup_inventory,
        "physical_rehearsal_observation": physical_rehearsal_observation,
        "physical_rehearsal_receipt": physical_rehearsal_receipt,
        "prepared_fence_context": prepared_fence_context,
        "release_probe_credential": release_probe_credential,
        "release_source_manifest": release_source_manifest,
        "retained_identity": retained_identity,
    }
    clone_certificate = directory / "clone-certificate.json"
    create_clone_certificate(
        restore_receipt_path=restore_receipt,
        output_path=clone_certificate,
        candidate_snapshot=candidate,
    )
    return {
        "directory": directory,
        "source": source,
        "candidate": candidate,
        "promoted": promoted,
        "artifacts": artifacts,
        "clone_certificate": clone_certificate,
    }


def _healthy_services() -> dict[str, object]:
    return {
        "api": {
            "status": "ok",
            "service": "CareSync",
            "version": "1.0.0",
            "databaseName": "caresync",
            "databaseIntegrity": "ok",
        },
        "frontend": {
            "status": "ok",
            "sha256Body": _digest("CareSync frontend"),
        },
    }


def _live_runtime_state(fixture: dict[str, object]) -> dict[str, object]:
    return {
        "revision": TARGET_REVISION,
        "identity": copy.deepcopy(fixture["source"]["identity"]),
        "billingPolicyProfile": "A",
        "runtimeCertificate": {
            "hook": "Database.assert_basic_runtime_identity",
            "status": "passed",
        },
    }


def test_source_candidate_requires_exact_unchanged_business_projection() -> None:
    source = _snapshot(
        revision=SOURCE_REVISION,
        identity=_identity(
            port=5434,
            data_directory="/source",
            system_identifier="source-system",
        ),
    )
    candidate = _snapshot(
        revision=TARGET_REVISION,
        identity=_identity(
            port=56555,
            data_directory="/clone",
            system_identifier="clone-system",
        ),
    )
    verify_source_candidate(source, candidate)

    changed = copy.deepcopy(candidate)
    for table in changed["business"]["tables"]:
        if table["name"] == "families":
            table["sha256Rows"] = _digest("changed families")
    with pytest.raises(ReleaseContractError, match="changed pre-existing"):
        verify_source_candidate(source, changed)

    same_cluster = copy.deepcopy(candidate)
    same_cluster["identity"]["systemIdentifier"] = source["identity"][
        "systemIdentifier"
    ]
    with pytest.raises(ReleaseContractError, match="not a distinct"):
        verify_source_candidate(source, same_cluster)


def test_source_candidate_requires_all_four_new_tables_empty() -> None:
    source = _snapshot(
        revision=SOURCE_REVISION,
        identity=_identity(
            port=5434,
            data_directory="/source",
            system_identifier="source-system",
        ),
    )
    candidate = _snapshot(
        revision=TARGET_REVISION,
        identity=_identity(
            port=56555,
            data_directory="/clone",
            system_identifier="clone-system",
        ),
    )
    candidate["new0041TableCounts"]["staff_room_presence_events"] = 1
    with pytest.raises(ReleaseContractError, match="0041 table count evidence"):
        verify_source_candidate(source, candidate)


def test_target_snapshot_requires_profile_a_and_passed_runtime_hook() -> None:
    source = _snapshot(
        revision=SOURCE_REVISION,
        identity=_identity(
            port=5434,
            data_directory="/source",
            system_identifier="source-system",
        ),
    )
    candidate = _snapshot(
        revision=TARGET_REVISION,
        identity=_identity(
            port=56555,
            data_directory="/clone",
            system_identifier="clone-system",
        ),
    )

    profile_b = copy.deepcopy(candidate)
    profile_b["billingPolicyProfile"] = "B"
    with pytest.raises(ReleaseContractError, match="billing-policy profile"):
        verify_source_candidate(source, profile_b)

    unchecked_runtime = copy.deepcopy(candidate)
    unchecked_runtime["runtimeCertificate"]["status"] = "not_required"
    with pytest.raises(ReleaseContractError, match="required hook"):
        verify_source_candidate(source, unchecked_runtime)


def test_private_receipt_is_no_clobber_and_rejects_symlinks_and_hardlinks(
    tmp_path: Path,
) -> None:
    directory = _private_directory(tmp_path)
    receipt = directory / "candidate.json"
    write_private_json_no_clobber(receipt, {"safe": "first"})
    assert stat.S_IMODE(receipt.stat().st_mode) == 0o600
    assert receipt.stat().st_nlink == 1
    with pytest.raises(ReleaseContractError, match="Refusing to replace"):
        write_private_json_no_clobber(receipt, {"safe": "second"})

    real_parent = tmp_path / "real"
    real_parent.mkdir(mode=0o700)
    real_parent.chmod(0o700)
    linked_parent = tmp_path / "linked"
    linked_parent.symlink_to(real_parent, target_is_directory=True)
    with pytest.raises(ReleaseContractError, match="symbolic link"):
        write_private_json_no_clobber(linked_parent / "unsafe.json", {"safe": True})

    original = _private_bytes(directory, "original.bin", b"one inode")
    alias = directory / "alias.bin"
    os.link(original, alias)
    with pytest.raises(ReleaseContractError, match="single-link"):
        bind_private_artifact(original, label="hard-linked artifact")


def test_atomic_rename_never_replaces_an_existing_path(tmp_path: Path) -> None:
    directory = _private_directory(tmp_path)
    source = directory / "source"
    source.mkdir(mode=0o700)
    destination = directory / "destination"
    atomic_rename_no_replace(source, destination)
    assert destination.is_dir()
    assert not source.exists()

    collision = directory / "collision"
    collision.mkdir(mode=0o700)
    with pytest.raises(ReleaseContractError, match="absent destination"):
        atomic_rename_no_replace(collision, destination)
    assert collision.is_dir()
    assert destination.is_dir()


def test_durable_private_publication_replace_and_fence_rename(
    tmp_path: Path,
) -> None:
    directory = _private_directory(tmp_path)
    source = _private_bytes(directory, "source.pending", b"first")
    destination = directory / "published.evidence"
    durable_publish_private_file(source, destination)
    assert destination.read_bytes() == b"first"
    assert not source.exists()

    replacement = _private_bytes(directory, "replacement.pending", b"second")
    durable_publish_private_file(
        replacement,
        destination,
        replace_existing=True,
    )
    assert destination.read_bytes() == b"second"
    collision = _private_bytes(directory, "collision.pending", b"third")
    with pytest.raises(ReleaseContractError, match="Refusing to replace"):
        durable_publish_private_file(collision, destination)
    assert collision.exists()
    assert destination.read_bytes() == b"second"

    pending_fence = directory / "fence.pending"
    ensure_private_directory(pending_fence)
    _private_bytes(pending_fence, "context", b"status=prepared\n")
    active_fence = directory / "fence"
    durable_rename_private_fence_no_replace(pending_fence, active_fence)
    assert not pending_fence.exists()
    assert (active_fence / "context").read_bytes() == b"status=prepared\n"

    second = directory / "second.pending"
    ensure_private_directory(second)
    _private_bytes(second, "context", b"status=prepared\n")
    with pytest.raises(ReleaseContractError, match="absent"):
        durable_rename_private_fence_no_replace(second, active_fence)
    assert second.is_dir()


def test_durable_private_removal_publishes_absence_and_rejects_links(
    tmp_path: Path,
) -> None:
    directory = _private_directory(tmp_path)
    target = _private_bytes(directory, "managed.pid", b"123\n")
    durable_remove_private_file(target)
    assert not target.exists()

    original = _private_bytes(directory, "linked.pid", b"456\n")
    alias = directory / "alias.pid"
    os.link(original, alias)
    with pytest.raises(ReleaseContractError, match="single-link"):
        durable_remove_private_file(original)
    assert original.exists()
    assert alias.exists()


def test_durable_private_removal_republishes_absence_after_torn_unlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    directory = _private_directory(tmp_path)
    absent = directory / "already-unlinked.pid"
    barriers: list[int] = []
    monkeypatch.setattr(
        basic_release_contract,
        "full_sync_fd",
        lambda descriptor: barriers.append(descriptor),
    )

    durable_remove_private_file(absent)

    assert len(barriers) == 1
    assert not absent.exists()


def test_durable_fence_and_tree_barrier_reject_unbound_entries(
    tmp_path: Path,
) -> None:
    directory = _private_directory(tmp_path)
    tree = directory / "tree"
    ensure_private_directory(tree)
    _private_bytes(tree, "artifact", b"durable")
    nested = tree / "nested"
    ensure_private_directory(nested)
    _private_bytes(nested, "receipt", b"closed")
    durability_barrier_private_tree(tree)

    linked = tree / "linked"
    linked.symlink_to(tree / "artifact")
    with pytest.raises(ReleaseContractError, match="symbolic"):
        durability_barrier_private_tree(tree)
    linked.unlink()

    malformed_fence = directory / "malformed.pending"
    ensure_private_directory(malformed_fence)
    _private_bytes(malformed_fence, "context", b"status=prepared\n")
    _private_bytes(malformed_fence, "extra", b"not closed")
    with pytest.raises(ReleaseContractError, match="exactly one"):
        durable_rename_private_fence_no_replace(
            malformed_fence,
            directory / "malformed-active",
        )


def test_receipt_writer_rejects_credential_like_material(tmp_path: Path) -> None:
    directory = _private_directory(tmp_path)
    with pytest.raises(ReleaseContractError, match="credential-like"):
        write_private_json_no_clobber(
            directory / "unsafe.json",
            {"note": "postgresql://operator:do-not-store@127.0.0.1/caresync"},
        )


def test_artifact_inventory_is_closed_and_optional_groups_are_all_or_none() -> None:
    validate_artifact_names(
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
    with pytest.raises(ReleaseContractError, match="Unknown"):
        validate_artifact_names(
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
                "surprise",
            }
        )
    with pytest.raises(ReleaseContractError, match="group is partial"):
        validate_artifact_names(
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
                "family_vault_bundle",
            }
        )


def test_clone_certificate_requires_a_strong_empty_restore_target(
    tmp_path: Path,
) -> None:
    fixture = _release_fixture(tmp_path)
    original = json.loads(
        fixture["artifacts"]["database_restore_receipt"].read_text(encoding="utf-8")
    )
    original["strongTargetAttestation"]["targetWasEmpty"] = False
    invalid = _private_json(
        fixture["directory"],
        "not-empty.restore.receipt.json",
        original,
    )
    with pytest.raises(ReleaseContractError, match="not attested as completely empty"):
        create_clone_certificate(
            restore_receipt_path=invalid,
            output_path=fixture["directory"] / "should-not-exist.json",
            candidate_snapshot=fixture["candidate"],
        )


def test_physical_rehearsal_is_bound_to_retained_source_and_manifest(
    tmp_path: Path,
) -> None:
    fixture = _release_fixture(tmp_path)
    artifacts = fixture["artifacts"]
    receipt = verify_physical_rehearsal_receipt(
        rehearsal_receipt_path=artifacts["physical_rehearsal_receipt"],
        rehearsal_observation_path=artifacts["physical_rehearsal_observation"],
        physical_backup_manifest_path=artifacts["physical_backup_manifest"],
        physical_backup_inventory_path=artifacts["physical_backup_inventory"],
        retained_identity_path=artifacts["retained_identity"],
        expected_source_snapshot=fixture["source"],
    )
    assert receipt["phase"] == "physical_backup_rehearsed_and_stopped"
    assert receipt["onlineAttestation"] == {
        "endpoint": "127.0.0.1:56556",
        "isInRecovery": False,
        "writerRoleStates": {
            "caresync_basic_app": "nologin",
            "caresync_transport_evidence_ingest": "nologin",
        },
        "otherClientSessions": 0,
    }

    unsafe_receipt = json.loads(
        artifacts["physical_rehearsal_receipt"].read_text(encoding="utf-8")
    )
    unsafe_receipt["onlineAttestation"]["otherClientSessions"] = 1
    unsafe_receipt_path = _private_json(
        fixture["directory"],
        "unsafe-rehearsal.receipt.json",
        unsafe_receipt,
    )
    with pytest.raises(ReleaseContractError, match="online isolation"):
        verify_physical_rehearsal_receipt(
            rehearsal_receipt_path=unsafe_receipt_path,
            rehearsal_observation_path=artifacts[
                "physical_rehearsal_observation"
            ],
            physical_backup_manifest_path=artifacts["physical_backup_manifest"],
            physical_backup_inventory_path=artifacts["physical_backup_inventory"],
            retained_identity_path=artifacts["retained_identity"],
        )

    changed_source = copy.deepcopy(fixture["source"])
    changed_source["business"]["sha256Rows"] = _digest("not the base backup")
    with pytest.raises(ReleaseContractError, match="not the retained source"):
        verify_physical_rehearsal_receipt(
            rehearsal_receipt_path=artifacts["physical_rehearsal_receipt"],
            rehearsal_observation_path=artifacts[
                "physical_rehearsal_observation"
            ],
            physical_backup_manifest_path=artifacts["physical_backup_manifest"],
            physical_backup_inventory_path=artifacts["physical_backup_inventory"],
            retained_identity_path=artifacts["retained_identity"],
            expected_source_snapshot=changed_source,
        )

    artifacts["physical_backup_manifest"].write_bytes(b"tampered manifest")
    with pytest.raises(ReleaseContractError, match="no longer matches"):
        verify_physical_rehearsal_receipt(
            rehearsal_receipt_path=artifacts["physical_rehearsal_receipt"],
            rehearsal_observation_path=artifacts[
                "physical_rehearsal_observation"
            ],
            physical_backup_manifest_path=artifacts["physical_backup_manifest"],
            physical_backup_inventory_path=artifacts["physical_backup_inventory"],
            retained_identity_path=artifacts["retained_identity"],
        )


def test_physical_inventory_covers_ignored_config_and_wal_bytes(
    tmp_path: Path,
) -> None:
    directory = _private_directory(tmp_path)
    pgdata = directory / "postgres-data"
    pgdata.mkdir(mode=0o700)
    pgdata.chmod(0o700)
    wal = pgdata / "pg_wal"
    wal.mkdir(mode=0o700)
    wal.chmod(0o700)
    for path, payload in (
        (pgdata / "PG_VERSION", b"17\n"),
        (pgdata / "postgresql.auto.conf", b"archive_command='false'\n"),
        (wal / "000000010000000000000001", b"wal bytes"),
    ):
        path.write_bytes(payload)
        path.chmod(0o600)
    # macOS can attach quarantine/provenance metadata to temporary fixtures;
    # Linux runners do not ship the macOS xattr executable and do not need
    # this cleanup.
    xattr_tool = Path("/usr/bin/xattr")
    if xattr_tool.is_file():
        subprocess.run(
            [str(xattr_tool), "-cr", str(pgdata)],
            check=True,
        )

    inventory = directory / "physical.inventory.json"
    created = create_physical_backup_inventory(
        pgdata=pgdata,
        output_path=inventory,
    )
    assert {
        entry["path"] for entry in created["entries"] if entry["type"] == "file"
    } == {
        "PG_VERSION",
        "postgresql.auto.conf",
        "pg_wal/000000010000000000000001",
    }
    verify_physical_backup_inventory(pgdata=pgdata, inventory_path=inventory)
    (pgdata / "postgresql.auto.conf").write_bytes(b"tampered")
    with pytest.raises(ReleaseContractError, match="complete inventory"):
        verify_physical_backup_inventory(pgdata=pgdata, inventory_path=inventory)


def test_candidate_and_commit_receipts_bind_the_complete_release(
    tmp_path: Path,
) -> None:
    fixture = _release_fixture(tmp_path)
    directory = fixture["directory"]
    release_payload = directory / "release-payload.json"
    candidate_receipt = directory / "candidate-receipt.json"
    receipt = create_candidate_receipt(
        source_snapshot=fixture["source"],
        clone_certificate_path=fixture["clone_certificate"],
        artifact_paths=fixture["artifacts"],
        release_payload_path=release_payload,
        receipt_path=candidate_receipt,
    )
    assert receipt["format"] == CANDIDATE_RECEIPT_FORMAT
    assert set(receipt["artifacts"]) == {
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
        "clone_certificate",
        "release_payload",
    }
    verified_candidate = verify_candidate_receipt(
        receipt_path=candidate_receipt,
        clone_certificate_path=fixture["clone_certificate"],
        release_payload_path=release_payload,
        artifact_paths=fixture["artifacts"],
    )
    assert verified_candidate["releaseId"] == receipt["releaseId"]

    commit_receipt = directory / "commit-receipt.json"
    commit = create_commit_receipt(
        candidate_receipt_path=candidate_receipt,
        clone_certificate_path=fixture["clone_certificate"],
        release_payload_path=release_payload,
        artifact_paths=fixture["artifacts"],
        promoted_snapshot=fixture["promoted"],
        receipt_path=commit_receipt,
    )
    assert commit["format"] == COMMIT_RECEIPT_FORMAT
    assert commit["releaseId"] == receipt["releaseId"]
    assert (
        verify_commit_receipt(
            commit_receipt_path=commit_receipt,
            candidate_receipt_path=candidate_receipt,
            clone_certificate_path=fixture["clone_certificate"],
            release_payload_path=release_payload,
            artifact_paths=fixture["artifacts"],
        )["releaseId"]
        == receipt["releaseId"]
    )

    with pytest.raises(ReleaseContractError, match="Refusing to replace"):
        create_commit_receipt(
            candidate_receipt_path=candidate_receipt,
            clone_certificate_path=fixture["clone_certificate"],
            release_payload_path=release_payload,
            artifact_paths=fixture["artifacts"],
            promoted_snapshot=fixture["promoted"],
            receipt_path=commit_receipt,
        )

    assert (
        verify_live_commit_state(
            current_promoted_snapshot=fixture["promoted"],
            commit_receipt_path=commit_receipt,
            candidate_receipt_path=candidate_receipt,
            clone_certificate_path=fixture["clone_certificate"],
            release_payload_path=release_payload,
            artifact_paths=fixture["artifacts"],
        )["releaseId"]
        == receipt["releaseId"]
    )
    finalization_receipt = directory / "finalization-receipt.json"
    finalization = create_finalization_receipt(
        commit_receipt_path=commit_receipt,
        candidate_receipt_path=candidate_receipt,
        clone_certificate_path=fixture["clone_certificate"],
        release_payload_path=release_payload,
        artifact_paths=fixture["artifacts"],
        current_live_state=_live_runtime_state(fixture),
        health_evidence=_healthy_services(),
        receipt_path=finalization_receipt,
    )
    assert finalization["phase"] == "healthy"
    assert (
        verify_finalization_receipt(
            finalization_receipt_path=finalization_receipt,
            commit_receipt_path=commit_receipt,
            candidate_receipt_path=candidate_receipt,
            clone_certificate_path=fixture["clone_certificate"],
            release_payload_path=release_payload,
            artifact_paths=fixture["artifacts"],
        )["releaseId"]
        == receipt["releaseId"]
    )


def test_artifact_tamper_and_receipt_shape_drift_are_rejected(tmp_path: Path) -> None:
    fixture = _release_fixture(tmp_path)
    directory = fixture["directory"]
    payload = directory / "release-payload.json"
    receipt_path = directory / "candidate-receipt.json"
    receipt = create_candidate_receipt(
        source_snapshot=fixture["source"],
        clone_certificate_path=fixture["clone_certificate"],
        artifact_paths=fixture["artifacts"],
        release_payload_path=payload,
        receipt_path=receipt_path,
    )

    drifted = copy.deepcopy(receipt)
    drifted["unexpected"] = True
    with pytest.raises(ReleaseContractError, match="unsupported JSON shape"):
        _validate_candidate_receipt(drifted)

    fixture["artifacts"]["backup"].write_bytes(b"tampered but still private")
    with pytest.raises(ReleaseContractError, match="no longer matches"):
        verify_candidate_receipt(
            receipt_path=receipt_path,
            clone_certificate_path=fixture["clone_certificate"],
            release_payload_path=payload,
            artifact_paths=fixture["artifacts"],
        )


def test_resume_requires_the_exact_original_0039_snapshot(tmp_path: Path) -> None:
    fixture = _release_fixture(tmp_path)
    directory = fixture["directory"]
    payload = directory / "release-payload.json"
    receipt_path = directory / "candidate-receipt.json"
    create_candidate_receipt(
        source_snapshot=fixture["source"],
        clone_certificate_path=fixture["clone_certificate"],
        artifact_paths=fixture["artifacts"],
        release_payload_path=payload,
        receipt_path=receipt_path,
    )
    certified = certify_source_resume(
        current_source_snapshot=fixture["source"],
        candidate_receipt_path=receipt_path,
        clone_certificate_path=fixture["clone_certificate"],
        release_payload_path=payload,
        artifact_paths=fixture["artifacts"],
    )
    assert certified["sourceRevision"] == SOURCE_REVISION

    changed_source = copy.deepcopy(fixture["source"])
    changed_source["business"]["sha256Rows"] = _digest("changed source")
    with pytest.raises(ReleaseContractError, match="not the source captured"):
        certify_source_resume(
            current_source_snapshot=changed_source,
            candidate_receipt_path=receipt_path,
            clone_certificate_path=fixture["clone_certificate"],
            release_payload_path=payload,
            artifact_paths=fixture["artifacts"],
        )


def test_resume_authorization_is_bound_no_clobber_and_independently_verified(
    tmp_path: Path,
) -> None:
    fixture = _release_fixture(tmp_path)
    directory = fixture["directory"]
    payload = directory / "release-payload.json"
    receipt_path = directory / "candidate-receipt.json"
    create_candidate_receipt(
        source_snapshot=fixture["source"],
        clone_certificate_path=fixture["clone_certificate"],
        artifact_paths=fixture["artifacts"],
        release_payload_path=payload,
        receipt_path=receipt_path,
    )
    authorization_path = directory / "resume-0039.authorization.json"
    authorization = create_resume_authorization(
        current_source_snapshot=fixture["source"],
        candidate_receipt_path=receipt_path,
        clone_certificate_path=fixture["clone_certificate"],
        release_payload_path=payload,
        artifact_paths=fixture["artifacts"],
        authorization_path=authorization_path,
    )
    assert authorization["phase"] == "resume_0039"
    assert (
        verify_resume_authorization(
            authorization_path=authorization_path,
            current_source_snapshot=fixture["source"],
            candidate_receipt_path=receipt_path,
            clone_certificate_path=fixture["clone_certificate"],
            release_payload_path=payload,
            artifact_paths=fixture["artifacts"],
        )["releaseId"]
        == authorization["releaseId"]
    )

    with pytest.raises(ReleaseContractError, match="Refusing to replace"):
        create_resume_authorization(
            current_source_snapshot=fixture["source"],
            candidate_receipt_path=receipt_path,
            clone_certificate_path=fixture["clone_certificate"],
            release_payload_path=payload,
            artifact_paths=fixture["artifacts"],
            authorization_path=authorization_path,
        )

    changed = copy.deepcopy(fixture["source"])
    changed["business"]["sha256Rows"] = _digest("state changed after authorization")
    with pytest.raises(ReleaseContractError, match="not the source captured"):
        verify_resume_authorization(
            authorization_path=authorization_path,
            current_source_snapshot=changed,
            candidate_receipt_path=receipt_path,
            clone_certificate_path=fixture["clone_certificate"],
            release_payload_path=payload,
            artifact_paths=fixture["artifacts"],
        )


def test_receipts_contain_hashes_but_no_artifact_paths_or_secret_values(
    tmp_path: Path,
) -> None:
    fixture = _release_fixture(tmp_path)
    directory = fixture["directory"]
    payload = directory / "release-payload.json"
    receipt_path = directory / "candidate-receipt.json"
    create_candidate_receipt(
        source_snapshot=fixture["source"],
        clone_certificate_path=fixture["clone_certificate"],
        artifact_paths=fixture["artifacts"],
        release_payload_path=payload,
        receipt_path=receipt_path,
    )
    serialized = receipt_path.read_text(encoding="utf-8")
    parsed = json.loads(serialized)
    assert "/Users/" not in serialized
    assert "postgresql://" not in serialized
    assert "password" not in serialized.lower()
    assert (
        parsed["artifacts"]["backup"]["sha256"]
        == hashlib.sha256(fixture["artifacts"]["backup"].read_bytes()).hexdigest()
    )
