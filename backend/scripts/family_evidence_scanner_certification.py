"""Synthetic-only, opt-in certification for the real family-evidence scanner.

The harness calls the production ``scan_private_object`` adapter through the
same inode-pinned ``PrivateObjectHandle`` used by the family-authority API. It
creates only short-lived synthetic files, never opens a database or socket,
and emits a redacted mode-0600 no-clobber receipt outside the source tree.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.basic.family_evidence_vault import (
    MalwareScanResult,
    PrivateObjectHandle,
    ScannerUnavailable,
    scan_private_object,
)
from app.core.config import BACKEND_ROOT, Settings
from scripts.family_evidence_vault_reconcile import (
    EvidenceVaultReconcileError,
    write_reconcile_report,
)

CERTIFICATION_FORMAT = "caresync-family-evidence-scanner-certification-v1"
OPT_IN_ENVIRONMENT = "CARESYNC_RUN_REAL_SCANNER_CERTIFICATION"
OPT_IN_VALUE = "synthetic-only"


class FamilyEvidenceScannerCertificationError(RuntimeError):
    """Raised when the bounded scanner proof cannot be completed safely."""


def _harmless_antivirus_test_bytes() -> bytes:
    """Build the standard inert antivirus test string without storing it whole."""

    fragments = (
        "X5O!P%@AP[4\\PZX54(P^)7CC)7}$",
        "EICAR-STANDARD-ANTIVIRUS-TEST-FILE",
        "!$H+H*",
    )
    value = "".join(fragments).encode("ascii")
    if len(value) != 68:
        raise FamilyEvidenceScannerCertificationError(
            "Synthetic antivirus fixture failed its fixed-length invariant"
        )
    return value


def _failing_scan_executable_bytes(observed_at: datetime) -> bytes:
    """Return a scanner double whose version succeeds and scan phase fails."""

    definition_time = observed_at.astimezone(UTC).strftime("%a %b %d %H:%M:%S %Y")
    return (
        "#!/bin/sh\n"
        'if [ "$1" = "--version" ]; then\n'
        f"  printf '%s\\n' 'ClamAV synthetic/1/{definition_time}'\n"
        "  exit 0\n"
        "fi\n"
        "exit 2\n"
    ).encode("ascii")


def _write_private_fixture(path: Path, content: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    descriptor = os.open(path, flags, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        remaining = memoryview(content)
        while remaining:
            written = os.write(descriptor, remaining)
            if written < 1:
                raise OSError("Synthetic fixture write made no progress")
            remaining = remaining[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _scan_fixture(path: Path, settings: Settings) -> MalwareScanResult:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    descriptor = os.open(path, flags)
    with PrivateObjectHandle(
        descriptor=descriptor,
        storage_reference="synthetic-certification-only",
    ) as handle:
        handle.validate_private_inode(settings.family_evidence_max_bytes)
        return scan_private_object(handle, settings)


def _scanner_settings(
    scanner_path: Path,
    *,
    work_root: Path,
    timeout_seconds: float,
    maximum_definition_age_hours: int,
) -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        database_type="sqlite",
        database_path=work_root / "caresync.db",
        database_read_only=True,
        family_evidence_scanner_path=scanner_path,
        family_evidence_scanner_timeout_seconds=timeout_seconds,
        family_evidence_scanner_max_definition_age_hours=maximum_definition_age_hours,
    )


def _expect_fail_closed(
    fixture: Path,
    settings: Settings,
    *,
    expected_reason: str,
) -> dict[str, Any]:
    try:
        _scan_fixture(fixture, settings)
    except ScannerUnavailable as error:
        observed_reason = str(error)
        if observed_reason != expected_reason:
            raise FamilyEvidenceScannerCertificationError(
                "Scanner failed closed with an unexpected bounded reason"
            ) from error
        return {
            "expected": "fail_closed",
            "observed": "fail_closed",
            "reasonCode": observed_reason,
            "passed": True,
        }
    raise FamilyEvidenceScannerCertificationError(
        "Scanner infrastructure failure did not fail closed"
    )


def _validate_completed_receipt_payload(payload: dict[str, Any]) -> None:
    """Reject incomplete or expanded evidence before it becomes a receipt."""

    expected_top_level = {
        "format",
        "generatedAt",
        "result",
        "scope",
        "scanner",
        "cases",
        "redaction",
    }
    if set(payload) != expected_top_level:
        raise FamilyEvidenceScannerCertificationError(
            "Certification payload is incomplete or contains unapproved fields"
        )
    if payload.get("format") != CERTIFICATION_FORMAT or payload.get("result") != "passed":
        raise FamilyEvidenceScannerCertificationError(
            "Only a completed certification can produce a receipt"
        )
    generated_at = payload.get("generatedAt")
    if not isinstance(generated_at, str):
        raise FamilyEvidenceScannerCertificationError(
            "Certification payload has no valid generation time"
        )
    try:
        parsed_generated_at = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    except ValueError as error:
        raise FamilyEvidenceScannerCertificationError(
            "Certification payload has no valid generation time"
        ) from error
    if parsed_generated_at.tzinfo is None or parsed_generated_at.utcoffset() is None:
        raise FamilyEvidenceScannerCertificationError(
            "Certification generation time must include a timezone"
        )

    expected_scope = {
        "syntheticOnly": True,
        "databaseOpened": False,
        "networkOpenedByHarness": False,
        "retainedDataAccessed": False,
        "alembicInvoked": False,
        "releaseAuthority": False,
        "cutoverAuthority": False,
    }
    expected_redaction = {
        "fixtureBytesRecorded": False,
        "fixturePathsRecorded": False,
        "scannerAbsolutePathRecorded": False,
        "signatureValueRecorded": False,
    }
    expected_cases = {
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
    }
    if payload.get("scope") != expected_scope:
        raise FamilyEvidenceScannerCertificationError(
            "Certification scope does not prove the bounded synthetic run"
        )
    if payload.get("redaction") != expected_redaction:
        raise FamilyEvidenceScannerCertificationError(
            "Certification redaction contract is incomplete"
        )
    if payload.get("cases") != expected_cases:
        raise FamilyEvidenceScannerCertificationError(
            "Certification cases are incomplete or did not all pass"
        )

    scanner = payload.get("scanner")
    if not isinstance(scanner, dict) or set(scanner) != {
        "engine",
        "version",
        "executableName",
        "definitionFreshnessEnforced",
        "maximumDefinitionAgeHours",
    }:
        raise FamilyEvidenceScannerCertificationError(
            "Certification scanner identity is incomplete"
        )
    engine = scanner.get("engine")
    executable_name = scanner.get("executableName")
    maximum_age = scanner.get("maximumDefinitionAgeHours")
    if (
        not isinstance(engine, str)
        or re.fullmatch(r"[A-Za-z0-9._-]{1,80}", engine) is None
        or not isinstance(executable_name, str)
        or re.fullmatch(r"[A-Za-z0-9._-]{1,255}", executable_name) is None
        or scanner.get("definitionFreshnessEnforced") is not True
        or isinstance(maximum_age, bool)
        or not isinstance(maximum_age, int)
        or not 1 <= maximum_age <= 720
    ):
        raise FamilyEvidenceScannerCertificationError(
            "Certification scanner policy is invalid"
        )
    version = scanner.get("version")
    if not isinstance(version, str) or re.fullmatch(
        r"ClamAV [A-Za-z0-9][A-Za-z0-9._+-]{0,79}/[1-9][0-9]*/"
        r"[A-Z][a-z]{2} [A-Z][a-z]{2} [0-9]{1,2} "
        r"[0-9]{2}:[0-9]{2}:[0-9]{2} [0-9]{4}",
        version,
    ) is None:
        raise FamilyEvidenceScannerCertificationError(
            "Certification scanner version is not canonical"
        )


def certify_family_evidence_scanner(
    scanner_path: Path,
    *,
    opt_in: str | None,
    timeout_seconds: float = 60.0,
    maximum_definition_age_hours: int = 168,
) -> dict[str, Any]:
    """Run the four synthetic cases and return a redacted receipt payload."""

    if opt_in != OPT_IN_VALUE:
        raise FamilyEvidenceScannerCertificationError(
            f"Set {OPT_IN_ENVIRONMENT}={OPT_IN_VALUE} to run the synthetic proof"
        )
    scanner_path = scanner_path.expanduser()
    if not scanner_path.is_absolute():
        raise FamilyEvidenceScannerCertificationError("Scanner path must be absolute")
    if not 1.0 <= timeout_seconds <= 300.0:
        raise FamilyEvidenceScannerCertificationError(
            "Scanner timeout must be between 1 and 300 seconds"
        )
    if not 1 <= maximum_definition_age_hours <= 720:
        raise FamilyEvidenceScannerCertificationError(
            "Maximum definition age must be between 1 and 720 hours"
        )

    with tempfile.TemporaryDirectory(prefix="caresync-family-scanner-cert-") as temporary:
        work_root = Path(temporary)
        work_root.chmod(0o700)
        clean_fixture = work_root / "clean.synthetic"
        antivirus_fixture = work_root / "antivirus-test.synthetic"
        failure_scanner = work_root / "scanner-failure.synthetic"
        _write_private_fixture(
            clean_fixture,
            b"CareSync synthetic family-evidence scanner certification.\n",
        )
        _write_private_fixture(antivirus_fixture, _harmless_antivirus_test_bytes())
        _write_private_fixture(
            failure_scanner,
            _failing_scan_executable_bytes(datetime.now(UTC)),
        )
        failure_scanner.chmod(0o700)

        real_settings = _scanner_settings(
            scanner_path,
            work_root=work_root,
            timeout_seconds=timeout_seconds,
            maximum_definition_age_hours=maximum_definition_age_hours,
        )
        try:
            clean = _scan_fixture(clean_fixture, real_settings)
        except ScannerUnavailable as error:
            raise FamilyEvidenceScannerCertificationError(
                f"Real scanner failed closed before the clean verdict: {error}"
            ) from None
        if (
            clean.decision != "clean"
            or clean.reason_code is not None
            or clean.scanner_signature is not None
        ):
            raise FamilyEvidenceScannerCertificationError(
                "Real scanner did not return the required clean verdict"
            )

        try:
            rejected = _scan_fixture(antivirus_fixture, real_settings)
        except ScannerUnavailable as error:
            raise FamilyEvidenceScannerCertificationError(
                f"Real scanner failed closed before the rejection verdict: {error}"
            ) from None
        if (
            rejected.decision != "rejected"
            or rejected.reason_code != "malware_detected"
            or not rejected.scanner_signature
        ):
            raise FamilyEvidenceScannerCertificationError(
                "Real scanner did not reject the harmless antivirus test signature"
            )
        if (
            rejected.scanner_engine != clean.scanner_engine
            or rejected.scanner_version != clean.scanner_version
        ):
            raise FamilyEvidenceScannerCertificationError(
                "Real scanner identity changed between synthetic verdicts"
            )

        unavailable_settings = _scanner_settings(
            work_root / "missing-scanner",
            work_root=work_root,
            timeout_seconds=timeout_seconds,
            maximum_definition_age_hours=maximum_definition_age_hours,
        )
        unavailable = _expect_fail_closed(
            clean_fixture,
            unavailable_settings,
            expected_reason="configured_scanner_unavailable",
        )
        failure_settings = _scanner_settings(
            failure_scanner,
            work_root=work_root,
            timeout_seconds=timeout_seconds,
            maximum_definition_age_hours=maximum_definition_age_hours,
        )
        failure = _expect_fail_closed(
            clean_fixture,
            failure_settings,
            expected_reason="malware_scanner_failed",
        )

    return {
        "format": CERTIFICATION_FORMAT,
        "generatedAt": datetime.now(UTC).isoformat(),
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
            "engine": clean.scanner_engine,
            "version": clean.scanner_version,
            "executableName": scanner_path.name,
            "definitionFreshnessEnforced": True,
            "maximumDefinitionAgeHours": maximum_definition_age_hours,
        },
        "cases": {
            "clean": {
                "expected": "clean",
                "observed": clean.decision,
                "passed": True,
            },
            "harmlessAntivirusTestSignature": {
                "expected": "rejected",
                "observed": rejected.decision,
                "reasonCode": rejected.reason_code,
                "signatureObserved": True,
                "signatureRedacted": True,
                "passed": True,
            },
            "scannerUnavailable": unavailable,
            "scannerFailure": failure,
        },
        "redaction": {
            "fixtureBytesRecorded": False,
            "fixturePathsRecorded": False,
            "scannerAbsolutePathRecorded": False,
            "signatureValueRecorded": False,
        },
    }


def write_private_certification_receipt(path: Path, payload: dict[str, Any]) -> Path:
    """Write one redacted, private, no-clobber certification receipt."""

    absolute = Path(os.path.abspath(os.path.expanduser(os.fspath(path))))
    backend_root = Path(os.path.abspath(os.fspath(BACKEND_ROOT)))
    if not path.is_absolute():
        raise FamilyEvidenceScannerCertificationError("Receipt path must be absolute")
    if absolute == backend_root or backend_root in absolute.parents:
        raise FamilyEvidenceScannerCertificationError(
            "Certification receipts must remain outside the backend source tree"
        )
    _validate_completed_receipt_payload(payload)
    try:
        write_reconcile_report(absolute, payload)
    except EvidenceVaultReconcileError as error:
        raise FamilyEvidenceScannerCertificationError(
            "Certification receipt could not be written privately without clobbering"
        ) from error
    details = absolute.stat(follow_symlinks=False)
    expected_owner = os.geteuid() if hasattr(os, "geteuid") else details.st_uid
    if (
        not stat.S_ISREG(details.st_mode)
        or stat.S_IMODE(details.st_mode) != 0o600
        or details.st_nlink != 1
        or details.st_uid != expected_owner
    ):
        raise FamilyEvidenceScannerCertificationError(
            "Certification receipt did not remain a private single-link file"
        )
    return absolute


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Certify CareSync's real scanner with synthetic-only fixtures."
    )
    parser.add_argument(
        "--synthetic-only",
        action="store_true",
        help="Required acknowledgement that only bundled synthetic fixtures may be used.",
    )
    parser.add_argument("--scanner", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=60.0)
    parser.add_argument("--maximum-definition-age-hours", type=int, default=168)
    args = parser.parse_args()
    if not args.synthetic_only:
        parser.error("--synthetic-only is required")
    try:
        payload = certify_family_evidence_scanner(
            args.scanner,
            opt_in=os.getenv(OPT_IN_ENVIRONMENT),
            timeout_seconds=args.timeout_seconds,
            maximum_definition_age_hours=args.maximum_definition_age_hours,
        )
        receipt = write_private_certification_receipt(args.receipt, payload)
    except FamilyEvidenceScannerCertificationError as error:
        parser.error(str(error))
    print(json.dumps({"result": "passed", "receipt": os.fspath(receipt)}))


if __name__ == "__main__":
    main()
