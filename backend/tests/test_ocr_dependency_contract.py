"""Release contract for the isolated server-side OCR environment."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = BACKEND_ROOT.parent
OCR_REQUIREMENTS = BACKEND_ROOT / "scripts" / "ocr-requirements.txt"
OCR_LOCK = (
    BACKEND_ROOT
    / "scripts"
    / "ocr-requirements-linux-x86_64-cp312.lock"
)
OCR_CERTIFIER = BACKEND_ROOT / "scripts" / "certify_ocr_runtime.py"
OCR_LOCK_SHA256 = "690443224983f90dae019da7c74306656430fe2dc490dcb37a3dd92209c5e81f"

EXPECTED_REQUIREMENTS = {
    "paddlepaddle": "3.3.1",
    "paddleocr": "3.7.0",
    "paddlex[ocr-core]": "3.7.2",
    "opencv-contrib-python": "4.10.0.84",
    "pymupdf": "1.28.0",
}


def _exact_pins() -> dict[str, str]:
    pins: dict[str, str] = {}
    for raw_line in OCR_REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        assert line.count("==") == 1, f"OCR dependency must be exactly pinned: {line}"
        name, version = line.split("==", 1)
        assert name not in pins, f"duplicate OCR dependency: {name}"
        pins[name] = version
    return pins


def test_ocr_runtime_uses_the_resolved_cpython_312_linux_set() -> None:
    assert _exact_pins() == EXPECTED_REQUIREMENTS


def test_ocr_runtime_has_only_one_opencv_provider() -> None:
    pins = _exact_pins()
    providers = {
        name
        for name in pins
        if name
        in {
            "opencv-python",
            "opencv-python-headless",
            "opencv-contrib-python",
            "opencv-contrib-python-headless",
        }
    }

    assert providers == {"opencv-contrib-python"}


def test_ocr_lock_is_complete_exact_and_content_addressed() -> None:
    lock_bytes = OCR_LOCK.read_bytes()
    assert hashlib.sha256(lock_bytes).hexdigest() == OCR_LOCK_SHA256

    entries: dict[str, tuple[str, str]] = {}
    pattern = re.compile(
        r"^(?P<name>[A-Za-z0-9_.-]+(?:\[[A-Za-z0-9_,.-]+\])?)"
        r"==(?P<version>[^\s]+) --hash=sha256:(?P<digest>[0-9a-f]{64})$"
    )
    for raw_line in lock_bytes.decode("utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = pattern.fullmatch(line)
        assert match is not None, f"OCR lock entry is not exact and hashed: {line}"
        name = match.group("name").casefold().replace("_", "-")
        assert name not in entries, f"duplicate OCR lock dependency: {name}"
        entries[name] = (match.group("version"), match.group("digest"))

    assert len(entries) == 65
    for name, expected_version in EXPECTED_REQUIREMENTS.items():
        normalized = name.casefold().replace("_", "-")
        assert entries[normalized][0] == expected_version


def test_deployer_installs_and_certifies_the_same_ocr_contract() -> None:
    deployer = (
        REPOSITORY_ROOT / "deploy" / "scripts" / "deploy-release.sh"
    ).read_text(encoding="utf-8")

    validator = deployer[
        deployer.index("validate_ocr_runtime()")
        : deployer.index("capture_ocr_runtime_baseline()")
    ]
    certifier = OCR_CERTIFIER.read_text(encoding="utf-8")
    stage = deployer[
        deployer.index('ocr_candidate_stage="$(')
        : deployer.index("capture_ocr_runtime_baseline", deployer.index('ocr_candidate_stage="$('))
    ]

    assert "ocr-requirements-linux-x86_64-cp312.lock" in deployer
    assert '--requirement "$ocr_lock_path"' in deployer
    assert "--require-hashes" in deployer
    assert "--only-binary=:all:" in deployer
    assert '"$ocr_candidate_stage/bin/python" -m pip check' in deployer
    assert 'if cv2.__version__ != "4.10.0":' in certifier
    assert "if actual != expected:" in certifier
    assert "raise SystemExit" in certifier
    assert "assert " not in validator
    assert "assert " not in certifier
    assert "runuser -u caresync -- env" in validator
    assert 'cd "$ocr_home"' in validator
    assert "certify_ocr_runtime_permissions" in validator
    assert "certify_ocr_runtime.py" in validator
    assert 'installed.pop("pip", None)' in certifier
    assert "actual != expected" in certifier
    assert "chown -R root:caresync" in deployer
    assert "chmod -R u=rwX,g=rX,o=" in deployer
    assert "! -user root" in deployer
    assert "! -group caresync" in deployer
    assert "-perm /0027" in deployer
    assert stage.index("-m pip check") < stage.index(
        "normalize_ocr_runtime_permissions"
    )
    assert stage.index("normalize_ocr_runtime_permissions") < stage.index(
        'validate_ocr_runtime "$ocr_candidate_stage"'
    )
    assert stage.index('validate_ocr_runtime "$ocr_candidate_stage"') < stage.index(
        'mv -T -- "$ocr_candidate_stage" "$ocr_candidate"'
    )
    assert 'rm -rf -- "$ocr_candidate"' not in deployer
    assert "paddlepaddle==" not in deployer


def test_ci_and_release_archive_use_the_hashed_ocr_lock() -> None:
    workflow = (
        REPOSITORY_ROOT / ".github" / "workflows" / "ci-cd.yml"
    ).read_text(encoding="utf-8")
    archive_validator = (
        REPOSITORY_ROOT / "deploy" / "scripts" / "validate-release-archive.py"
    ).read_text(encoding="utf-8")

    assert "--require-hashes" in workflow
    assert "ocr-requirements-linux-x86_64-cp312.lock" in workflow
    assert "ocr-requirements-linux-x86_64-cp312.lock" in archive_validator


def test_ocr_activation_and_recovery_share_the_live_mutation_fence() -> None:
    deployer = (
        REPOSITORY_ROOT / "deploy" / "scripts" / "deploy-release.sh"
    ).read_text(encoding="utf-8")
    recovery_trap = deployer.index("trap 'recover_failed_deployment")
    service_stop = deployer.index(
        'systemctl stop "$push_service_name" "$service_name"',
        recovery_trap,
    )
    activation = deployer.index("\nactivate_ocr_runtime\n", service_stop)
    app_pointer = deployer.index(
        'ln -sfn "$release_path" "$current_link.next"',
        activation,
    )
    recovery = deployer[
        deployer.index("recover_failed_deployment()")
        : deployer.index("\ntrap cleanup EXIT")
    ]

    assert "capture_ocr_runtime_baseline" in deployer[:recovery_trap]
    assert recovery_trap < service_stop < activation < app_pointer
    assert "ocr_mutated=1" in deployer[
        deployer.index("activate_ocr_runtime()")
        : deployer.index("restore_ocr_runtime_baseline()")
    ]
    assert "restore_ocr_runtime_baseline" in recovery
    assert recovery.index("restore_ocr_runtime_baseline") < recovery.index(
        'ln -sfn "$previous_target" "$current_link.rollback"'
    )
    assert "trap 'recovery_interrupted=1' INT TERM HUP" in recovery
    assert "trap - ERR INT TERM HUP" not in recovery


def test_same_release_fast_path_certifies_service_user_ocr_first() -> None:
    deployer = (
        REPOSITORY_ROOT / "deploy" / "scripts" / "deploy-release.sh"
    ).read_text(encoding="utf-8")
    fast_path = deployer.index('if [[ "$release_already_active" -eq 1 ]]')
    success = deployer.index(
        'echo "CareSync release $release_sha is already active and healthy."',
        fast_path,
    )

    assert deployer.index("capture_ocr_runtime_baseline", 0, fast_path) < fast_path
    assert deployer.index("ocr_runtime_matches_expected", fast_path, success) < success
    assert deployer.index("certify_local_health", fast_path, success) < success


def test_manual_rollback_refuses_an_incompatible_ocr_runtime() -> None:
    rollback = (
        REPOSITORY_ROOT / "deploy" / "scripts" / "rollback-release.sh"
    ).read_text(encoding="utf-8")
    stop = rollback.index(
        'systemctl stop "$push_service_name" "$service_name"'
    )
    compatibility = rollback.index("certify_target_ocr_runtime")
    refusal = rollback.index(
        "Rollback refused: the target release does not match "
        "the active certified OCR runtime."
    )

    assert "ocr-requirements-linux-x86_64-cp312.lock" in rollback
    assert "certify_ocr_runtime.py" in rollback
    assert "runuser -u caresync -- env" in rollback
    assert "target_ocr_candidate" in rollback
    assert "requirements.sha256" in rollback
    assert compatibility < refusal < stop


def test_worker_rejects_an_unsupported_opencv_major() -> None:
    worker = (BACKEND_ROOT / "scripts" / "ocr_worker.py").read_text(encoding="utf-8")

    assert "(4, 10) <= opencv_version < (5, 0)" in worker
    assert '"engine": "opencv+paddleocr"' in worker
    assert "opencv5" not in worker.casefold()
