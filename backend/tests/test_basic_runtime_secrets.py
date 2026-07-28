"""Private local runtime-secret persistence and fail-closed checks."""

from __future__ import annotations

import base64
import os
import stat
from pathlib import Path

import pytest

from scripts.basic_runtime_secrets import (
    SECRET_DIRECTORY_NAME,
    STAFF_SCREENING_KEY_FILE,
    TRANSPORT_INGEST_PASSWORD_FILE,
    RuntimeSecretError,
    ensure_runtime_secrets,
)
from scripts.configure_basic_runtime_credentials import (
    RuntimeCredentialError,
    _scram_verifier,
    _transport_password,
    _verifier_matches,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _runtime(tmp_path: Path) -> Path:
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    return runtime


def _value(path: Path) -> str:
    raw = path.read_text(encoding="ascii")
    assert raw.endswith("\n")
    value = raw[:-1]
    assert "\n" not in value
    assert len(base64.urlsafe_b64decode(value + "=")) == 32
    return value


def test_runtime_secrets_are_private_distinct_and_stable(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)

    ensure_runtime_secrets(runtime)
    secret_directory = runtime / SECRET_DIRECTORY_NAME
    staff_key = secret_directory / STAFF_SCREENING_KEY_FILE
    transport_password = secret_directory / TRANSPORT_INGEST_PASSWORD_FILE
    first = (_value(staff_key), _value(transport_password))

    ensure_runtime_secrets(runtime)
    second = (_value(staff_key), _value(transport_password))

    assert first == second
    assert first[0] != first[1]
    assert stat.S_IMODE(secret_directory.stat().st_mode) == 0o700
    assert stat.S_IMODE(staff_key.stat().st_mode) == 0o600
    assert stat.S_IMODE(transport_password.stat().st_mode) == 0o600


def test_runtime_secret_refuses_broad_file_mode(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    ensure_runtime_secrets(runtime)
    key = runtime / SECRET_DIRECTORY_NAME / STAFF_SCREENING_KEY_FILE
    key.chmod(0o640)

    with pytest.raises(RuntimeSecretError, match="private regular file"):
        ensure_runtime_secrets(runtime)


def test_runtime_secret_refuses_link_substitution(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    secret_directory = runtime / SECRET_DIRECTORY_NAME
    secret_directory.mkdir(mode=0o700)
    outside = tmp_path / "outside"
    outside.write_text("A" * 43 + "\n", encoding="ascii")
    os.symlink(outside, secret_directory / STAFF_SCREENING_KEY_FILE)

    with pytest.raises(RuntimeSecretError):
        ensure_runtime_secrets(runtime)


def test_runtime_secret_refuses_corrupt_value(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    ensure_runtime_secrets(runtime)
    key = runtime / SECRET_DIRECTORY_NAME / STAFF_SCREENING_KEY_FILE
    key.write_text("not-a-key\n", encoding="ascii")
    key.chmod(0o600)

    with pytest.raises(RuntimeSecretError, match="invalid format"):
        ensure_runtime_secrets(runtime)


def test_transport_credential_builds_a_non_plaintext_scram_verifier(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    ensure_runtime_secrets(runtime)
    password = _transport_password(runtime)

    verifier = _scram_verifier(password, salt=b"0123456789abcdef")

    assert verifier.startswith("SCRAM-SHA-256$4096:")
    assert password not in verifier
    assert _verifier_matches(password, verifier)
    assert not _verifier_matches(password[::-1], verifier)
    assert not _verifier_matches(password, "md5-not-accepted")


def test_transport_credential_reader_reuses_runtime_secret_safety(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    ensure_runtime_secrets(runtime)
    password = runtime / SECRET_DIRECTORY_NAME / TRANSPORT_INGEST_PASSWORD_FILE
    password.chmod(0o640)

    with pytest.raises(RuntimeCredentialError, match="absent or unsafe"):
        _transport_password(runtime)


def test_launcher_creates_and_forwards_stable_private_runtime_secrets() -> None:
    launcher = (PROJECT_ROOT / "scripts" / "start-basic.sh").read_text(encoding="utf-8")
    release = (PROJECT_ROOT / "scripts" / "basic-release.sh").read_text(
        encoding="utf-8"
    )

    ensure_position = launcher.index("python scripts/basic_runtime_secrets.py")
    credential_position = launcher.index(
        "scripts/configure_basic_runtime_credentials.py"
    )
    api_position = launcher.index(
        '"$ROOT/backend/scripts/gated_service_exec.py" hold',
        credential_position,
    )
    migration_position = release.index(
        "/bin/bash ./scripts/uv.sh run alembic upgrade"
    )
    bootstrap_position = release.index(
        "bootstrap_basic_runtime_role.sql",
        migration_position,
    )
    controlled_start_position = release.index(
        '"$RELEASE_EXECUTION_ROOT/scripts/start-basic.sh"',
        bootstrap_position,
    )

    assert ensure_position < credential_position < api_position
    assert migration_position < bootstrap_position < controlled_start_position
    assert "alembic upgrade" not in launcher
    assert "bootstrap_basic_runtime_role.sql" not in launcher
    assert "staff-screening-vault.key" in launcher
    assert "transport-evidence-ingest.password" in launcher
    assert launcher.count(
        'STAFF_SCREENING_VAULT_ENCRYPTION_KEY="$STAFF_SCREENING_VAULT_ENCRYPTION_KEY"'
    ) >= 2
    assert launcher.count(
        'TRANSPORT_EVIDENCE_INGEST_PASSWORD="$TRANSPORT_EVIDENCE_INGEST_PASSWORD"'
    ) >= 2
    assert "CareSync private runtime secrets are invalid; refusing startup" in launcher
    assert '--runtime-directory "$RUNTIME_DIR"' in launcher
    assert '--migration-user "$MIGRATION_USER"' in launcher
