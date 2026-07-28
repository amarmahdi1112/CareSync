"""Fail-closed configuration continuity for captured CareSync Basic launches.

The release source deliberately excludes ``.env`` files.  This bridge reads the
installed backend's protected external ``.env`` without evaluating it as shell
code, selects only reviewed non-database Settings fields, validates them using
the captured Settings model, and execs the launcher with those values in the
process environment.  Configuration values are never written or printed.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import logging
import os
import re
import stat
import sys
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

from dotenv import dotenv_values
from dotenv.parser import parse_stream
from pydantic import ValidationError

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

MAX_ENV_BYTES = 1024 * 1024
RUNTIME_CONFIG_MARKER = "caresync-basic-runtime-config-v1"

# Every Settings field must remain explicitly classified.  The launcher owns
# database identity, network binding, release mode, billing activation and
# private-vault placement.  Those values must never leak in from an ordinary
# development environment or the installed .env.
RELEASE_CONTROLLED_FIELDS = frozenset(
    {
        "app_name",
        "environment",
        "host",
        "port",
        "database_type",
        "database_path",
        "database_name",
        "database_host",
        "database_port",
        "database_user",
        "database_password",
        "transport_evidence_ingest_user",
        "transport_evidence_ingest_password",
        "database_ssl",
        "database_read_only",
        "enable_advanced_routes",
        "billing_mode",
        "billing_sandbox_target_attestation",
        "billing_sandbox_organization_ids",
        "billing_manual_target_attestation",
        "billing_manual_organization_ids",
        "family_evidence_vault_path",
        "staff_screening_vault_path",
        "staff_screening_vault_encryption_key",
    }
)

# These are the complete non-database settings whose ordinary installed-source
# semantics must survive a launch from an immutable captured source.
CONTINUITY_FIELDS = frozenset(
    {
        "app_version",
        "api_prefix",
        "allowed_origins",
        "extension_origin_regex",
        "child_profile_photo_max_bytes",
        "child_profile_photo_max_pixels",
        "child_profile_photo_max_edge",
        "family_evidence_max_bytes",
        "family_evidence_max_image_pixels",
        "family_evidence_max_pdf_pages",
        "family_evidence_parser_timeout_seconds",
        "family_evidence_scanner_path",
        "family_evidence_scanner_timeout_seconds",
        "family_evidence_scanner_max_definition_age_hours",
        "staff_screening_vault_key_id",
        "staff_screening_document_max_bytes",
        "scheduler_engine_version",
        "jwt_secret",
        "jwt_expires_in",
        "gemini_api_key",
        "gemini_model",
        "deepseek_api_key",
        "deepseek_model",
        "deepseek_name_match_threshold",
        "deepseek_name_match_chunk_size",
        "deepseek_name_match_max_provider_calls",
        "deepseek_name_match_deadline_seconds",
        "push_delivery_enabled",
        "push_provider",
        "expo_push_access_token",
        "push_provider_timeout_seconds",
    }
)

_JWT_LIFETIME_PATTERN = re.compile(r"^[1-9][0-9]*(?:[mhdMHD])?$")


class RuntimeConfigError(RuntimeError):
    """A generic, value-free configuration continuity failure."""


def _settings_class() -> type[Any]:
    from app.core.config import Settings

    return Settings


def _classified_field_names() -> frozenset[str]:
    settings_fields = frozenset(_settings_class().model_fields)
    classified = RELEASE_CONTROLLED_FIELDS | CONTINUITY_FIELDS
    if (
        RELEASE_CONTROLLED_FIELDS & CONTINUITY_FIELDS
        or settings_fields != classified
    ):
        raise RuntimeConfigError(
            "CareSync runtime Settings classification is incomplete; refusing startup"
        )
    return settings_fields


def _read_all(file_descriptor: int, expected_size: int) -> bytes:
    if expected_size > MAX_ENV_BYTES:
        raise RuntimeConfigError(
            "CareSync external runtime configuration is too large; refusing startup"
        )
    chunks: list[bytes] = []
    remaining = MAX_ENV_BYTES + 1
    while remaining:
        chunk = os.read(file_descriptor, min(64 * 1024, remaining))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    raw = b"".join(chunks)
    if len(raw) > MAX_ENV_BYTES:
        raise RuntimeConfigError(
            "CareSync external runtime configuration is too large; refusing startup"
        )
    return raw


def read_protected_env(path: Path) -> str | None:
    """Read an optional private .env through no-follow directory descriptors."""

    if not path.is_absolute() or any(part in {".", ".."} for part in path.parts):
        raise RuntimeConfigError(
            "CareSync external runtime configuration path is unsafe"
        )
    no_follow = getattr(os, "O_NOFOLLOW", None)
    if no_follow is None:
        raise RuntimeConfigError(
            "CareSync runtime cannot enforce no-follow configuration reads"
        )
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | no_follow
    file_flags = os.O_RDONLY | os.O_CLOEXEC | no_follow
    parts = path.parts
    if len(parts) < 2 or parts[0] != os.sep:
        raise RuntimeConfigError(
            "CareSync external runtime configuration path is unsafe"
        )

    directory_fd = os.open(os.sep, directory_flags)
    file_fd = -1
    try:
        try:
            for component in parts[1:-1]:
                next_fd = os.open(
                    component,
                    directory_flags,
                    dir_fd=directory_fd,
                )
                os.close(directory_fd)
                directory_fd = next_fd
            file_fd = os.open(parts[-1], file_flags, dir_fd=directory_fd)
        except FileNotFoundError:
            return None
        except OSError as error:
            raise RuntimeConfigError(
                "CareSync external runtime configuration is unavailable or unsafe"
            ) from error

        before = os.fstat(file_fd)
        mode = stat.S_IMODE(before.st_mode)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.getuid()
            or before.st_nlink != 1
            or mode & 0o077
            or not mode & stat.S_IRUSR
        ):
            raise RuntimeConfigError(
                "CareSync external runtime configuration must be an "
                "owner-private single-link regular file"
            )
        raw = _read_all(file_fd, before.st_size)
        after = os.fstat(file_fd)
        before_facts = (
            before.st_dev,
            before.st_ino,
            before.st_mode,
            before.st_uid,
            before.st_gid,
            before.st_nlink,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        after_facts = (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_uid,
            after.st_gid,
            after.st_nlink,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        if before_facts != after_facts or len(raw) != after.st_size:
            raise RuntimeConfigError(
                "CareSync external runtime configuration changed while being read"
            )
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise RuntimeConfigError(
                "CareSync external runtime configuration is not valid UTF-8"
            ) from None
        if "\x00" in text:
            raise RuntimeConfigError(
                "CareSync external runtime configuration contains invalid data"
            )
        return text
    finally:
        if file_fd >= 0:
            os.close(file_fd)
        os.close(directory_fd)


def parse_external_env(text: str | None) -> dict[str, str]:
    """Parse dotenv syntax without logging malformed lines or evaluating shell."""

    if text is None:
        return {}
    dotenv_logger = logging.getLogger("dotenv.main")
    was_disabled = dotenv_logger.disabled
    dotenv_logger.disabled = True
    try:
        try:
            bindings = tuple(parse_stream(io.StringIO(text)))
            if any(binding.error for binding in bindings):
                raise ValueError
            parsed = dotenv_values(stream=io.StringIO(text), interpolate=True)
        except Exception:  # noqa: BLE001 - never expose parser input in a traceback
            raise RuntimeConfigError(
                "CareSync external runtime configuration has invalid dotenv syntax"
            ) from None
    finally:
        dotenv_logger.disabled = was_disabled
    return {key: "" if value is None else value for key, value in parsed.items()}


def _recognized_values(
    values: Mapping[str, str],
    *,
    allowed_fields: frozenset[str],
) -> dict[str, str]:
    allowed = {field.casefold(): field.upper() for field in allowed_fields}
    selected: dict[str, str] = {}
    origins: dict[str, str] = {}
    for key, value in values.items():
        canonical = allowed.get(key.casefold())
        if canonical is None:
            continue
        if canonical in selected and origins[canonical] != key:
            raise RuntimeConfigError(
                "CareSync runtime configuration contains ambiguous key casing"
            )
        selected[canonical] = value
        origins[canonical] = key
    return selected


@contextlib.contextmanager
def _temporary_settings_environment(
    effective: Mapping[str, str],
    settings_fields: frozenset[str],
) -> Iterator[None]:
    recognized = {field.casefold() for field in settings_fields}
    saved = {
        key: value
        for key, value in os.environ.items()
        if key.casefold() in recognized
    }
    for key in tuple(os.environ):
        if key.casefold() in recognized:
            del os.environ[key]
    os.environ.update(effective)
    try:
        yield
    finally:
        for key in tuple(os.environ):
            if key.casefold() in recognized:
                del os.environ[key]
        os.environ.update(saved)


def _validate_effective_values(
    effective: Mapping[str, str],
    settings_fields: frozenset[str],
) -> None:
    try:
        with _temporary_settings_environment(effective, settings_fields):
            settings = _settings_class()(_env_file=None)
    except (OSError, TypeError, ValueError, ValidationError):
        raise RuntimeConfigError(
            "CareSync non-database runtime configuration is invalid"
        ) from None

    jwt_secret = settings.jwt_secret.get_secret_value()
    if (
        len(jwt_secret) < 32
        or jwt_secret.strip().casefold()
        in {"change-me", "changeme", "default", "secret", "test"}
    ):
        raise RuntimeConfigError(
            "CareSync JWT configuration is missing or unsafe; refusing startup"
        )
    if not _JWT_LIFETIME_PATTERN.fullmatch(settings.jwt_expires_in.strip()):
        raise RuntimeConfigError(
            "CareSync JWT lifetime configuration is invalid; refusing startup"
        )
    if not settings.api_prefix.startswith("/"):
        raise RuntimeConfigError(
            "CareSync API prefix configuration is invalid; refusing startup"
        )
    if not settings.gemini_model.strip() or not settings.deepseek_model.strip():
        raise RuntimeConfigError(
            "CareSync provider model configuration is invalid; refusing startup"
        )
    if settings.push_delivery_enabled and (
        settings.push_provider != "expo"
        or not settings.expo_push_access_token.get_secret_value().strip()
    ):
        raise RuntimeConfigError(
            "CareSync push delivery configuration is incomplete; refusing startup"
        )


def build_runtime_environment(
    *,
    inherited: Mapping[str, str],
    external: Mapping[str, str],
    external_backend_root: Path,
) -> dict[str, str]:
    """Return a sanitized exec environment with environment-over-dotenv priority."""

    settings_fields = _classified_field_names()
    dotenv_values_by_field = _recognized_values(
        external,
        allowed_fields=CONTINUITY_FIELDS,
    )
    inherited_values_by_field = _recognized_values(
        inherited,
        allowed_fields=CONTINUITY_FIELDS,
    )
    effective = {**dotenv_values_by_field, **inherited_values_by_field}

    scanner_key = "FAMILY_EVIDENCE_SCANNER_PATH"
    scanner_value = effective.get(scanner_key, "").strip()
    if scanner_value:
        scanner_path = Path(scanner_value).expanduser()
        if not scanner_path.is_absolute():
            scanner_path = external_backend_root / scanner_path
        effective[scanner_key] = str(scanner_path.absolute())

    _validate_effective_values(effective, settings_fields)

    recognized = {field.casefold() for field in settings_fields}
    child_environment = {
        key: value
        for key, value in inherited.items()
        if key.casefold() not in recognized
    }
    child_environment.update(effective)
    child_environment["CARESYNC_BASIC_RUNTIME_CONFIG_LOADED"] = RUNTIME_CONFIG_MARKER
    return child_environment


def _normalize_command(command: Sequence[str]) -> list[str]:
    normalized = list(command)
    if normalized[:1] == ["--"]:
        normalized = normalized[1:]
    if not normalized:
        raise RuntimeConfigError("CareSync runtime configuration exec command is missing")
    return normalized


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Load and validate protected CareSync runtime configuration"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    execute = subparsers.add_parser("exec")
    execute.add_argument("--source-env", type=Path, required=True)
    execute.add_argument("exec_command", nargs=argparse.REMAINDER)
    subparsers.add_parser("validate")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.command == "validate":
            if (
                os.environ.get("CARESYNC_BASIC_RUNTIME_CONFIG_LOADED")
                != RUNTIME_CONFIG_MARKER
            ):
                raise RuntimeConfigError(
                    "CareSync runtime configuration validation marker is absent"
                )
            build_runtime_environment(
                inherited=os.environ,
                external={},
                external_backend_root=BACKEND_ROOT,
            )
            return 0

        source_env = arguments.source_env.absolute()
        external = parse_external_env(read_protected_env(source_env))
        child_environment = build_runtime_environment(
            inherited=os.environ,
            external=external,
            external_backend_root=source_env.parent,
        )
        command = _normalize_command(arguments.exec_command)
        os.execvpe(command[0], command, child_environment)
    except RuntimeConfigError as error:
        print(str(error), file=sys.stderr)
        return 78
    except OSError:
        print(
            "CareSync runtime configuration bridge could not execute the launcher",
            file=sys.stderr,
        )
        return 78
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
