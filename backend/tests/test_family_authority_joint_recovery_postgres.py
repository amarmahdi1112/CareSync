"""Opt-in synthetic PostgreSQL 0029D joint recovery-consistency proof.

The caller owns both artifact creation and disposable target lifecycle.  This
test never provisions or migrates a database.  It runs only with the explicit
synthetic-only opt-in and requires a fresh caller-migrated exact-0029D target.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.core.config import Settings
from app.db.session import Database
from scripts.backup_database import _sha256_file
from scripts.family_authority_joint_recovery_certification import (
    JointRecoveryCertificationError,
    certify_joint_recovery,
    joint_disposable_confirmation,
)
from scripts.family_evidence_vault_bundle import verify_evidence_bundle
from scripts.restore_database import PROTECTED_POSTGRES_PORTS

SYNTHETIC_CONFIRMATION = "I CONFIRM SYNTHETIC ARTIFACTS"
pytestmark = pytest.mark.skipif(
    os.environ.get("CARESYNC_JOINT_RECOVERY_SYNTHETIC_ONLY") != SYNTHETIC_CONFIRMATION,
    reason="requires explicit synthetic-only joint-recovery integration opt-in",
)


def _required_path(name: str) -> Path:
    value = os.environ.get(name)
    if not value:
        pytest.fail(f"{name} is required for the opt-in joint recovery proof")
    return Path(value)


def _required_text(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        pytest.fail(f"{name} is required for the opt-in joint recovery proof")
    return value


def test_synthetic_0029d_database_and_vault_restore_as_one_artifact_set(
    tmp_path: Path,
) -> None:
    backup = _required_path("CARESYNC_JOINT_RECOVERY_BACKUP")
    manifest = _required_path("CARESYNC_JOINT_RECOVERY_MANIFEST")
    bundle = _required_path("CARESYNC_JOINT_RECOVERY_BUNDLE")
    bundle_manifest = _required_path("CARESYNC_JOINT_RECOVERY_BUNDLE_MANIFEST")
    expected_pgdata = _required_path("CARESYNC_JOINT_RECOVERY_EXPECTED_PGDATA")
    expected_system_identifier = _required_text(
        "CARESYNC_JOINT_RECOVERY_EXPECTED_SYSTEM_IDENTIFIER"
    )
    settings = Settings(database_read_only=False)
    assert settings.database_type == "postgres"
    assert settings.database_port not in PROTECTED_POSTGRES_PORTS

    evidence = verify_evidence_bundle(backup, manifest, bundle, bundle_manifest)
    confirmation = joint_disposable_confirmation(
        settings,
        expected_data_directory=expected_pgdata,
        expected_system_identifier=expected_system_identifier,
        backup_sha256=evidence["manifest"]["databaseBackup"]["sha256Compressed"],
        manifest_sha256=evidence["manifest"]["databaseBackup"]["sha256Manifest"],
        bundle_sha256=evidence["manifest"]["sha256Bundle"],
        bundle_manifest_sha256=_sha256_file(bundle_manifest),
    )
    shadow = Database(settings)
    try:
        with shadow.engine.begin() as connection:
            connection.exec_driver_sql("CREATE SCHEMA joint_recovery_shadow")
            connection.exec_driver_sql(
                "CREATE TABLE joint_recovery_shadow.protected_row ("
                "id integer PRIMARY KEY, version_num varchar(64) NOT NULL "
                "REFERENCES public.alembic_version(version_num) ON DELETE CASCADE)"
            )
            connection.exec_driver_sql(
                "INSERT INTO joint_recovery_shadow.protected_row (id,version_num) "
                "SELECT 1,version_num FROM public.alembic_version"
            )
    finally:
        shadow.dispose()

    try:
        with pytest.raises(JointRecoveryCertificationError, match="non-system schema"):
            certify_joint_recovery(
                backup,
                manifest,
                bundle,
                bundle_manifest,
                expected_data_directory=expected_pgdata,
                expected_system_identifier=expected_system_identifier,
                vault_destination=tmp_path / "restored-private-family-authority-vault",
                database_receipt=tmp_path / "receipts" / "database-restore.json",
                vault_receipt=tmp_path / "receipts" / "evidence-restore.json",
                joint_receipt=tmp_path / "receipts" / "joint-recovery.json",
                confirmation=confirmation,
                settings=settings,
            )
        shadow_check = Database(settings)
        try:
            with shadow_check.engine.connect() as connection:
                assert connection.exec_driver_sql(
                    "SELECT count(*) FROM joint_recovery_shadow.protected_row"
                ).scalar_one() == 1
        finally:
            shadow_check.dispose()
    finally:
        cleanup = Database(settings)
        try:
            with cleanup.engine.begin() as connection:
                connection.exec_driver_sql(
                    "DROP SCHEMA IF EXISTS joint_recovery_shadow CASCADE"
                )
        finally:
            cleanup.dispose()

    assert not (tmp_path / "receipts" / "database-restore.json").exists()
    assert not (tmp_path / "receipts" / "joint-recovery.json").exists()
    result = certify_joint_recovery(
        backup,
        manifest,
        bundle,
        bundle_manifest,
        expected_data_directory=expected_pgdata,
        expected_system_identifier=expected_system_identifier,
        vault_destination=tmp_path / "restored-private-family-authority-vault",
        database_receipt=tmp_path / "receipts" / "database-restore.json",
        vault_receipt=tmp_path / "receipts" / "evidence-restore.json",
        joint_receipt=tmp_path / "receipts" / "joint-recovery.json",
        confirmation=confirmation,
        settings=settings,
    )

    assert result["scope"]["recoveryConsistencyProven"] is True
    assert result["scope"]["sourceWriterQuiescenceProven"] is False
    assert result["scope"]["authoritativeSameSnapshotCaptureProven"] is False
    assert result["scope"]["cutoverAuthority"] is False
    assert result["scope"]["releaseAuthority"] is False
    assert result["scope"]["purgeAuthority"] is False
