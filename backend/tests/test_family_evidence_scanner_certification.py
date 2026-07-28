"""Safety and opt-in proof for the real family-evidence scanner harness."""

from __future__ import annotations

import json
import os
import stat
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from scripts.family_evidence_scanner_certification import (
    CERTIFICATION_FORMAT,
    OPT_IN_ENVIRONMENT,
    OPT_IN_VALUE,
    FamilyEvidenceScannerCertificationError,
    _failing_scan_executable_bytes,
    certify_family_evidence_scanner,
    write_private_certification_receipt,
)


def _completed_payload() -> dict:
    return {
        "format": CERTIFICATION_FORMAT,
        "generatedAt": "2026-07-22T08:22:57+00:00",
        "result": "passed",
        "scope": {
            "syntheticOnly": True,
            "databaseOpened": False,
            "networkOpenedByHarness": False,
            "retainedDataAccessed": False,
            "alembicInvoked": False,
            "releaseAuthority": False,
            "cutoverAuthority": False,
        },
        "scanner": {
            "engine": "clamscan",
            "version": "ClamAV 1.5.3/28068/Wed Jul 22 00:24:50 2026",
            "executableName": "clamscan",
            "definitionFreshnessEnforced": True,
            "maximumDefinitionAgeHours": 168,
        },
        "cases": {
            "clean": {
                "expected": "clean",
                "observed": "clean",
                "passed": True,
            },
            "harmlessAntivirusTestSignature": {
                "expected": "rejected",
                "observed": "rejected",
                "reasonCode": "malware_detected",
                "signatureObserved": True,
                "signatureRedacted": True,
                "passed": True,
            },
            "scannerUnavailable": {
                "expected": "fail_closed",
                "observed": "fail_closed",
                "reasonCode": "configured_scanner_unavailable",
                "passed": True,
            },
            "scannerFailure": {
                "expected": "fail_closed",
                "observed": "fail_closed",
                "reasonCode": "malware_scanner_failed",
                "passed": True,
            },
        },
        "redaction": {
            "fixtureBytesRecorded": False,
            "fixturePathsRecorded": False,
            "scannerAbsolutePathRecorded": False,
            "signatureValueRecorded": False,
        },
    }


def test_certification_requires_exact_explicit_opt_in(tmp_path: Path) -> None:
    with pytest.raises(
        FamilyEvidenceScannerCertificationError,
        match=OPT_IN_ENVIRONMENT,
    ):
        certify_family_evidence_scanner(
            tmp_path / "scanner-is-never-opened",
            opt_in=None,
        )


def test_private_receipt_is_redacted_mode_0600_and_no_clobber(tmp_path: Path) -> None:
    private_directory = tmp_path / "private-receipts"
    private_directory.mkdir(mode=0o700)
    receipt = private_directory / "scanner-certification.json"
    payload = _completed_payload()

    written = write_private_certification_receipt(receipt, payload)
    assert written == receipt
    assert stat.S_IMODE(receipt.stat().st_mode) == 0o600
    assert json.loads(receipt.read_text(encoding="utf-8")) == payload
    with pytest.raises(FamilyEvidenceScannerCertificationError, match="without clobbering"):
        write_private_certification_receipt(receipt, payload)


def test_private_receipt_rejects_incomplete_or_expanded_evidence(tmp_path: Path) -> None:
    private_directory = tmp_path / "private-receipts"
    private_directory.mkdir(mode=0o700)

    incomplete = _completed_payload()
    incomplete.pop("cases")
    incomplete_receipt = private_directory / "incomplete.json"
    with pytest.raises(FamilyEvidenceScannerCertificationError, match="incomplete"):
        write_private_certification_receipt(incomplete_receipt, incomplete)
    assert not incomplete_receipt.exists()

    expanded = _completed_payload()
    expanded["scanner"]["version"] += " /private/operator/path"
    expanded_receipt = private_directory / "expanded.json"
    with pytest.raises(FamilyEvidenceScannerCertificationError, match="canonical"):
        write_private_certification_receipt(expanded_receipt, expanded)
    assert not expanded_receipt.exists()


def test_synthetic_failure_double_passes_version_then_fails_scan(tmp_path: Path) -> None:
    scanner = tmp_path / "scanner-failure.synthetic"
    scanner.write_bytes(
        _failing_scan_executable_bytes(datetime(2026, 7, 22, 8, tzinfo=UTC))
    )
    scanner.chmod(0o700)

    version = subprocess.run(
        [scanner, "--version"],
        check=False,
        capture_output=True,
        text=True,
    )
    failed_scan = subprocess.run(
        [scanner, "--no-summary", "--alert-exceeds-max=yes", "-"],
        check=False,
        input=b"synthetic scanner failure probe",
        capture_output=True,
    )

    assert version.returncode == 0
    assert version.stdout == "ClamAV synthetic/1/Wed Jul 22 08:00:00 2026\n"
    assert failed_scan.returncode == 2


@pytest.mark.skipif(
    os.getenv(OPT_IN_ENVIRONMENT) != OPT_IN_VALUE
    or not os.getenv("CARESYNC_REAL_SCANNER_PATH"),
    reason=(
        "real scanner certification is synthetic-only and requires explicit environment opt-in"
    ),
)
def test_real_scanner_clean_rejection_and_fail_closed_cases(tmp_path: Path) -> None:
    scanner_path = Path(os.environ["CARESYNC_REAL_SCANNER_PATH"])
    payload = certify_family_evidence_scanner(
        scanner_path,
        opt_in=os.environ[OPT_IN_ENVIRONMENT],
    )

    assert payload["result"] == "passed"
    assert payload["scope"] == {
        "syntheticOnly": True,
        "databaseOpened": False,
        "networkOpenedByHarness": False,
        "retainedDataAccessed": False,
        "alembicInvoked": False,
        "releaseAuthority": False,
        "cutoverAuthority": False,
    }
    assert payload["cases"]["clean"]["observed"] == "clean"
    assert payload["cases"]["harmlessAntivirusTestSignature"] == {
        "expected": "rejected",
        "observed": "rejected",
        "reasonCode": "malware_detected",
        "signatureObserved": True,
        "signatureRedacted": True,
        "passed": True,
    }
    assert payload["cases"]["scannerUnavailable"]["reasonCode"] == (
        "configured_scanner_unavailable"
    )
    assert payload["cases"]["scannerFailure"]["reasonCode"] == "malware_scanner_failed"

    private_directory = tmp_path / "private-receipts"
    private_directory.mkdir(mode=0o700)
    receipt = write_private_certification_receipt(
        private_directory / "real-scanner.json",
        payload,
    )
    serialized = receipt.read_text(encoding="utf-8")
    assert os.fspath(scanner_path) not in serialized
    assert os.fspath(tmp_path) not in serialized
    assert "EICAR-STANDARD" not in serialized
    assert stat.S_IMODE(receipt.stat().st_mode) == 0o600
