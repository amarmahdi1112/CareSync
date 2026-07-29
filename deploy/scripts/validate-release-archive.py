#!/usr/bin/env python3
"""Fail closed before extracting a CareSync production release archive."""

from __future__ import annotations

import argparse
import json
import re
import tarfile
from pathlib import Path, PurePosixPath

MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
MAX_EXPANDED_BYTES = 1024 * 1024 * 1024
MAX_MEMBER_BYTES = 256 * 1024 * 1024
MAX_MEMBERS = 20_000
EXPECTED_REVISION = "0042_billing_policy_recert"
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
FORBIDDEN_COMPONENTS = {
    ".git",
    ".env",
    "node_modules",
    "backups",
    "storage",
    "uploads",
    "secrets",
}
REQUIRED_MEMBERS = {
    "release-manifest.json",
    "backend/alembic.ini",
    "backend/pyproject.toml",
    "backend/scripts/certify_ocr_runtime.py",
    "backend/scripts/ocr-requirements-linux-x86_64-cp312.lock",
    "backend/uv.lock",
    "frontend-redesign/dist/index.html",
    "deploy/scripts/deploy-release.sh",
}


class ArchiveError(RuntimeError):
    """The uploaded archive is not a bounded CareSync release."""


def _safe_member(member: tarfile.TarInfo) -> None:
    path = PurePosixPath(member.name)
    if (
        not member.name
        or member.name.startswith("/")
        or path.is_absolute()
        or ".." in path.parts
        or "." in path.parts
    ):
        raise ArchiveError("release archive contains an unsafe path")
    if not (member.isfile() or member.isdir()):
        raise ArchiveError("release archive contains a non-regular object")
    lowered = tuple(part.casefold() for part in path.parts)
    if any(part in FORBIDDEN_COMPONENTS for part in lowered):
        raise ArchiveError("release archive contains a forbidden runtime path")
    if any(part.startswith(".env.") for part in lowered):
        raise ArchiveError("release archive contains a forbidden environment file")
    if member.size < 0 or member.size > MAX_MEMBER_BYTES:
        raise ArchiveError("release archive contains an oversized member")


def validate(archive: Path, expected_sha: str) -> dict[str, object]:
    if not archive.is_file() or archive.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ArchiveError("release archive is absent or oversized")
    if not SHA_PATTERN.fullmatch(expected_sha):
        raise ArchiveError("expected release SHA is invalid")

    names: set[str] = set()
    expanded = 0
    manifest_bytes: bytes | None = None
    with tarfile.open(archive, mode="r:gz") as bundle:
        members = bundle.getmembers()
        if len(members) > MAX_MEMBERS:
            raise ArchiveError("release archive contains too many members")
        for member in members:
            _safe_member(member)
            if member.name in names:
                raise ArchiveError("release archive contains duplicate paths")
            names.add(member.name)
            expanded += member.size
            if expanded > MAX_EXPANDED_BYTES:
                raise ArchiveError("release archive expands beyond its limit")
            if member.name == "release-manifest.json":
                if member.size > 64 * 1024:
                    raise ArchiveError("release manifest is oversized")
                extracted = bundle.extractfile(member)
                if extracted is None:
                    raise ArchiveError("release manifest is unreadable")
                manifest_bytes = extracted.read(64 * 1024 + 1)

    missing = REQUIRED_MEMBERS - names
    if missing:
        raise ArchiveError("release archive is incomplete")
    if manifest_bytes is None:
        raise ArchiveError("release manifest is absent")
    try:
        manifest = json.loads(manifest_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ArchiveError("release manifest is invalid") from exc
    if not isinstance(manifest, dict):
        raise ArchiveError("release manifest is invalid")
    if manifest.get("schema") != "caresync-release-v1":
        raise ArchiveError("release manifest schema is unsupported")
    if manifest.get("git_sha") != expected_sha:
        raise ArchiveError("release manifest SHA does not match the deployment")
    if manifest.get("database_revision") != EXPECTED_REVISION:
        raise ArchiveError("release manifest database revision is not approved")
    origin = manifest.get("production_origin")
    if not isinstance(origin, str) or not origin.startswith("https://"):
        raise ArchiveError("release manifest production origin is invalid")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("expected_sha")
    args = parser.parse_args()
    validate(args.archive, args.expected_sha)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
