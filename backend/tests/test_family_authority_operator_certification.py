"""Safety and opt-in integration gates for family-authority operator proof."""

from __future__ import annotations

import os
import stat
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from scripts.family_authority_operator_certification import (
    CERTIFICATION_FORMAT,
    CONFIRMATION_ENVIRONMENT,
    OPT_IN_ENVIRONMENT,
    CertificationTarget,
    FamilyAuthorityOperatorCertificationError,
    _validate_completed_receipt_payload,
    _validate_observed_target,
    _validate_target,
    certify_family_authority_operator_flow,
    write_private_operator_receipt,
)


def _scratch_target(
    root: Path,
    *,
    port: int = 55473,
    host: str = "127.0.0.1",
) -> CertificationTarget:
    (root / "PG_VERSION").write_text("17\n", encoding="ascii")
    (root / "postmaster.pid").write_text("12345\n", encoding="ascii")
    root.chmod(0o700)
    (root / "PG_VERSION").chmod(0o600)
    (root / "postmaster.pid").chmod(0o600)
    return CertificationTarget(
        host=host,
        port=port,
        database="caresync",
        runtime_user="caresync_basic_app",
        runtime_password="",
        attestation_user="postgres",
        attestation_password="",
        expected_data_directory=root,
        expected_system_identifier="7665369510324610356",
    )


def _payload() -> dict:
    return {
        "format": CERTIFICATION_FORMAT,
        "generatedAt": datetime.now(UTC).isoformat(),
        "result": "passed",
        "scope": {
            "syntheticOnly": True,
            "publicHttpRoutes": True,
            "inProcessAsgi": True,
            "attestationSentinelHeld": True,
            "callerProvisionedDatabase": True,
            "databaseProvisionedByHarness": False,
            "alembicInvoked": False,
            "databaseDroppedOrTruncated": False,
            "protectedPortsContacted": False,
            "retainedDataAccessed": False,
            "releaseAuthority": False,
            "cutoverAuthority": False,
        },
        "target": {
            "hostClass": "loopback",
            "databaseName": "caresync",
            "runtimeRole": "caresync_basic_app",
            "revision": "0029D_release_checkout_writer",
            "systemIdentifierSha256": "a" * 64,
            "baselineTablesEmpty": True,
            "otherClientSessions": 0,
            "postflightSameSystemIdentifier": True,
            "postflightExactRevision": True,
            "postflightExpectedSyntheticRows": True,
            "postflightUnexpectedClientSessions": 0,
        },
        "scanner": {
            "engine": "clamscan",
            "version": "ClamAV 1.5.3/28068/Wed Jul 22 00:24:50 2026",
            "executableName": "clamscan",
            "definitionFreshnessEnforced": True,
        },
        "cases": {
            "ownerRegistration": True,
            "administratorInvitationActivation": True,
            "productionMultipartUpload": True,
            "uploadExactReplayNoDuplicateObject": True,
            "productionClamscanClean": True,
            "scanExactReplayNoDuplicateAssessment": True,
            "cleanDocumentDownload": True,
            "evidenceRecorded": True,
            "makerReviewRejected409": True,
            "makerReviewNoWriteAttested": True,
            "independentCheckerReview": True,
            "reviewedAuthorityActivation": True,
            "activationExactReplayNoDuplicateRows": True,
            "piiFreeRealtimeInvalidation": True,
            "publicRealtimeWebSocketReplay": True,
            "administrativeSummaryObserved": True,
        },
        "redaction": {
            "credentialsRecorded": False,
            "tokensRecorded": False,
            "emailsRecorded": False,
            "personNamesRecorded": False,
            "recordIdentifiersRecorded": False,
            "documentBytesRecorded": False,
            "vaultPathsRecorded": False,
            "databaseDataDirectoryRecorded": False,
            "scannerAbsolutePathRecorded": False,
        },
    }


@pytest.mark.parametrize("port", [5432, 5433, 5434, 0, 65536])
def test_target_guard_rejects_protected_or_invalid_ports(port: int) -> None:
    target = CertificationTarget(
        host="127.0.0.1",
        port=port,
        database="caresync",
        runtime_user="caresync_basic_app",
        runtime_password="",
        attestation_user="postgres",
        attestation_password="",
        expected_data_directory=Path("/does/not/matter"),
        expected_system_identifier="7665369510324610356",
    )
    with pytest.raises(
        FamilyAuthorityOperatorCertificationError,
        match="protected or invalid",
    ):
        _validate_target(target, opt_in="synthetic-only", confirmation="irrelevant")


def test_target_guard_requires_owned_prefixed_temp_cluster_and_exact_confirmation() -> None:
    with tempfile.TemporaryDirectory(prefix="caresync-authority-cert.", dir="/tmp") as temporary:
        target = _scratch_target(Path(temporary))
        _validate_target(
            target,
            opt_in="synthetic-only",
            confirmation=target.confirmation,
        )
        with pytest.raises(
            FamilyAuthorityOperatorCertificationError,
            match=CONFIRMATION_ENVIRONMENT,
        ):
            _validate_target(
                target,
                opt_in="synthetic-only",
                confirmation="wrong",
            )


def test_target_guard_rejects_remote_host_before_database_access() -> None:
    target = CertificationTarget(
        host="database.example.test",
        port=55473,
        database="caresync",
        runtime_user="caresync_basic_app",
        runtime_password="",
        attestation_user="postgres",
        attestation_password="",
        expected_data_directory=Path("/does/not/matter"),
        expected_system_identifier="7665369510324610356",
    )
    with pytest.raises(FamilyAuthorityOperatorCertificationError, match="loopback"):
        _validate_target(target, opt_in="synthetic-only", confirmation="irrelevant")


def test_receipt_shape_is_closed_private_single_link_and_no_clobber(tmp_path: Path) -> None:
    receipt_root = tmp_path / "receipts"
    receipt_root.mkdir(mode=0o700)
    receipt_root.chmod(0o700)
    receipt = receipt_root / "operator.json"
    payload = _payload()

    _validate_completed_receipt_payload(payload)
    written = write_private_operator_receipt(receipt, payload)
    details = written.stat(follow_symlinks=False)
    assert stat.S_IMODE(details.st_mode) == 0o600
    assert details.st_nlink == 1

    with pytest.raises(FamilyAuthorityOperatorCertificationError, match="without clobbering"):
        write_private_operator_receipt(receipt, payload)


@pytest.mark.parametrize(
    ("section", "key", "value"),
    [
        ("scope", "alembicInvoked", True),
        ("scope", "protectedPortsContacted", True),
        ("scope", "attestationSentinelHeld", False),
        ("target", "postflightSameSystemIdentifier", False),
        ("target", "postflightExpectedSyntheticRows", False),
        ("redaction", "tokensRecorded", True),
        ("cases", "makerReviewNoWriteAttested", False),
        ("cases", "activationExactReplayNoDuplicateRows", False),
        ("cases", "piiFreeRealtimeInvalidation", False),
        ("cases", "publicRealtimeWebSocketReplay", False),
    ],
)
def test_receipt_rejects_weakened_scope_or_redaction(
    section: str,
    key: str,
    value: bool,
) -> None:
    payload = _payload()
    payload[section][key] = value
    with pytest.raises(FamilyAuthorityOperatorCertificationError):
        _validate_completed_receipt_payload(payload)


def test_receipt_rejects_expanded_sensitive_shape() -> None:
    payload = _payload()
    payload["activationToken"] = "must-never-be-recorded"
    with pytest.raises(FamilyAuthorityOperatorCertificationError, match="unapproved fields"):
        _validate_completed_receipt_payload(payload)


def test_observed_server_address_must_be_loopback() -> None:
    with tempfile.TemporaryDirectory(prefix="caresync-authority-cert.", dir="/tmp") as temporary:
        target = _scratch_target(Path(temporary))
        identity = (
            "postgres",
            "caresync",
            "127.0.0.1/32",
            target.port,
            os.fspath(target.expected_data_directory),
            12345,
        )
        _validate_observed_target(
            target,
            identity=identity,
            system_identifier=target.expected_system_identifier,
            revisions=["0029D_release_checkout_writer"],
        )
        with pytest.raises(
            FamilyAuthorityOperatorCertificationError,
            match="server address is not loopback",
        ):
            _validate_observed_target(
                target,
                identity=(*identity[:2], "198.51.100.8/32", *identity[3:]),
                system_identifier=target.expected_system_identifier,
                revisions=["0029D_release_checkout_writer"],
            )


@pytest.mark.parametrize(
    "version",
    [
        "ClamAV ",
        "ClamAV /tmp/private/scanner",
        "ClamAV 1.5.3",
        "ClamAV 1.5.3/28068/Wed Jul 22 00:24:50 2026\nsecret",
        "ClamAV 1.5.3/28068/Wed Jul 22 24:24:50 2026",
    ],
)
def test_receipt_rejects_noncanonical_or_unsafe_scanner_version(version: str) -> None:
    payload = _payload()
    payload["scanner"]["version"] = version
    with pytest.raises(
        FamilyAuthorityOperatorCertificationError,
        match="non-canonical or unsafe",
    ):
        _validate_completed_receipt_payload(payload)


INTEGRATION_PORT = os.getenv("CARESYNC_FAMILY_AUTHORITY_CERT_TEST_PORT")
INTEGRATION_DATA_DIRECTORY = os.getenv("CARESYNC_FAMILY_AUTHORITY_CERT_TEST_DATA_DIRECTORY")
INTEGRATION_SYSTEM_IDENTIFIER = os.getenv("CARESYNC_FAMILY_AUTHORITY_CERT_TEST_SYSTEM_IDENTIFIER")
INTEGRATION_SCANNER = os.getenv("CARESYNC_FAMILY_AUTHORITY_CERT_TEST_SCANNER")


@pytest.mark.skipif(
    not all(
        (
            INTEGRATION_PORT,
            INTEGRATION_DATA_DIRECTORY,
            INTEGRATION_SYSTEM_IDENTIFIER,
            INTEGRATION_SCANNER,
        )
    ),
    reason="requires one explicitly confirmed empty pre-migrated 0029D scratch cluster",
)
def test_real_signed_in_operator_certification_on_caller_supplied_scratch() -> None:
    assert INTEGRATION_PORT is not None
    assert INTEGRATION_DATA_DIRECTORY is not None
    assert INTEGRATION_SYSTEM_IDENTIFIER is not None
    assert INTEGRATION_SCANNER is not None
    target = CertificationTarget(
        host="127.0.0.1",
        port=int(INTEGRATION_PORT),
        database="caresync",
        runtime_user="caresync_basic_app",
        runtime_password=os.getenv("CARESYNC_FAMILY_AUTHORITY_CERT_RUNTIME_PASSWORD", ""),
        attestation_user=os.getenv(
            "CARESYNC_FAMILY_AUTHORITY_CERT_TEST_ATTESTATION_USER", "postgres"
        ),
        attestation_password=os.getenv("CARESYNC_FAMILY_AUTHORITY_CERT_ATTESTATION_PASSWORD", ""),
        expected_data_directory=Path(INTEGRATION_DATA_DIRECTORY),
        expected_system_identifier=INTEGRATION_SYSTEM_IDENTIFIER,
    )
    payload = certify_family_authority_operator_flow(
        target,
        Path(INTEGRATION_SCANNER),
        opt_in=os.getenv(OPT_IN_ENVIRONMENT),
        confirmation=os.getenv(CONFIRMATION_ENVIRONMENT),
    )
    _validate_completed_receipt_payload(payload)
