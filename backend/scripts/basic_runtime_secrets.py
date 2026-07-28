"""Create stable owner-only secrets for the private local Basic runtime.

The launcher needs one encryption key for confidential staff evidence and one
distinct database credential for the restricted transport-evidence identity.
Those values must survive restarts, must never be written into the source tree,
and must never be printed by this helper.
"""

from __future__ import annotations

import argparse
import base64
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path

SECRET_DIRECTORY_NAME = "secrets"
STAFF_SCREENING_KEY_FILE = "staff-screening-vault.key"
TRANSPORT_INGEST_PASSWORD_FILE = "transport-evidence-ingest.password"
_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43}$")


class RuntimeSecretError(RuntimeError):
    """Raised when the private runtime-secret boundary is unsafe."""


@dataclass(frozen=True)
class SecretSpec:
    filename: str
    label: str


SECRET_SPECS = (
    SecretSpec(STAFF_SCREENING_KEY_FILE, "staff screening vault key"),
    SecretSpec(TRANSPORT_INGEST_PASSWORD_FILE, "transport evidence credential"),
)


def _directory_flags() -> int:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    return flags


def _file_flags() -> int:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    return flags


def _require_private_directory(descriptor: int, label: str) -> None:
    measured = os.fstat(descriptor)
    if not stat.S_ISDIR(measured.st_mode):
        raise RuntimeSecretError(f"{label} is not a directory")
    if hasattr(os, "geteuid") and measured.st_uid != os.geteuid():
        raise RuntimeSecretError(f"{label} is not owned by the current user")
    if measured.st_mode & 0o077:
        raise RuntimeSecretError(f"{label} must be owner-only")


def _read_secret(descriptor: int, label: str) -> str:
    measured = os.fstat(descriptor)
    if (
        not stat.S_ISREG(measured.st_mode)
        or measured.st_nlink != 1
        or (hasattr(os, "geteuid") and measured.st_uid != os.geteuid())
        or measured.st_mode & 0o077
        or measured.st_size < 2
        or measured.st_size > 128
    ):
        raise RuntimeSecretError(f"{label} is not a private regular file")
    chunks: list[bytes] = []
    remaining = 129
    while remaining:
        chunk = os.read(descriptor, remaining)
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    try:
        raw = b"".join(chunks).decode("ascii")
    except UnicodeDecodeError:
        raise RuntimeSecretError(f"{label} is not valid ASCII") from None
    if not raw.endswith("\n") or "\n" in raw[:-1]:
        raise RuntimeSecretError(f"{label} must contain exactly one terminated value")
    value = raw[:-1]
    if not _TOKEN_PATTERN.fullmatch(value):
        raise RuntimeSecretError(f"{label} has an invalid format")
    try:
        decoded = base64.urlsafe_b64decode(value + "=")
    except ValueError:
        raise RuntimeSecretError(f"{label} has an invalid encoding") from None
    if len(decoded) != 32:
        raise RuntimeSecretError(f"{label} must encode exactly 32 bytes")
    return value


def _new_value(*, excluding: set[str]) -> str:
    while True:
        value = base64.urlsafe_b64encode(os.urandom(32)).decode("ascii").rstrip("=")
        if value not in excluding:
            return value


def _open_or_create_secret(
    directory_descriptor: int,
    spec: SecretSpec,
    *,
    excluding: set[str],
) -> str:
    try:
        descriptor = os.open(spec.filename, _file_flags(), dir_fd=directory_descriptor)
    except FileNotFoundError:
        value = _new_value(excluding=excluding)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        try:
            descriptor = os.open(spec.filename, flags, 0o600, dir_fd=directory_descriptor)
        except FileExistsError:
            descriptor = os.open(spec.filename, _file_flags(), dir_fd=directory_descriptor)
        else:
            try:
                os.fchmod(descriptor, 0o600)
                payload = f"{value}\n".encode("ascii")
                offset = 0
                while offset < len(payload):
                    offset += os.write(descriptor, payload[offset:])
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            os.fsync(directory_descriptor)
            descriptor = os.open(spec.filename, _file_flags(), dir_fd=directory_descriptor)
    except OSError as exc:
        raise RuntimeSecretError(f"{spec.label} is absent or unsafe") from exc
    try:
        return _read_secret(descriptor, spec.label)
    finally:
        os.close(descriptor)


def ensure_runtime_secrets(runtime_directory: Path) -> None:
    """Create or validate the stable local secrets without returning them."""

    if not runtime_directory.is_absolute():
        raise RuntimeSecretError("Runtime directory must be absolute")
    try:
        runtime_descriptor = os.open(runtime_directory, _directory_flags())
    except OSError as exc:
        raise RuntimeSecretError("Runtime directory is absent or unsafe") from exc
    try:
        _require_private_directory(runtime_descriptor, "Runtime directory")
        try:
            os.mkdir(SECRET_DIRECTORY_NAME, 0o700, dir_fd=runtime_descriptor)
            os.fsync(runtime_descriptor)
        except FileExistsError:
            pass
        secret_descriptor = os.open(
            SECRET_DIRECTORY_NAME,
            _directory_flags(),
            dir_fd=runtime_descriptor,
        )
        try:
            _require_private_directory(secret_descriptor, "Runtime secret directory")
            values: set[str] = set()
            for spec in SECRET_SPECS:
                value = _open_or_create_secret(
                    secret_descriptor,
                    spec,
                    excluding=values,
                )
                if value in values:
                    raise RuntimeSecretError("Runtime secrets must be distinct")
                values.add(value)
        finally:
            os.close(secret_descriptor)
    finally:
        os.close(runtime_descriptor)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create or validate CareSync Basic private runtime secrets."
    )
    parser.add_argument("--runtime-directory", type=Path, required=True)
    return parser


def main() -> int:
    arguments = _parser().parse_args()
    ensure_runtime_secrets(arguments.runtime_directory)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
