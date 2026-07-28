"""Create and verify the private, content-addressed CareSync release source.

The retained release never executes migrations or health code from the mutable
checkout after preparation.  This helper copies the complete release-relevant
source closure into one owner-only run directory, writes a canonical manifest,
and reopens the closed inventory before it can be admitted into a candidate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

if __package__:
    from .darwin_durability import full_sync_fd
else:
    from darwin_durability import full_sync_fd


FORMAT = "caresync-private-release-source-v1"
EXCLUDED_DIRECTORIES = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        "__pycache__",
        "build",
        "coverage",
        "dist",
        "htmlcov",
        "node_modules",
    }
)
EXCLUDED_FILE_SUFFIXES = (".pyc", ".pyo", ".log")
RECURSIVE_ROOTS = (
    "backend/app",
    "backend/alembic",
    "backend/scripts",
    # Frontend contract tests and runtime validation import the canonical
    # entity contract from the repository root.
    "contracts",
    # Vite, TypeScript and CSS tooling may execute arbitrary top-level config
    # helpers. Capture the complete frontend source/config closure instead of
    # maintaining a fragile allowlist.
    "frontend-redesign",
    "scripts",
)
ROOT_FILES = (
    "package-lock.json",
    "package.json",
    "pyproject.toml",
    "uv.lock",
)
BACKEND_FILES = (
    ".python-version",
    "alembic.ini",
    "package-lock.json",
    "package.json",
    "pyproject.toml",
    "requirements-dev.txt",
    "requirements.txt",
    "uv.lock",
)
FRONTEND_FILES = (
    ".npmrc",
    "eslint.config.js",
    "eslint.config.mjs",
    "index.html",
    "package-lock.json",
    "package.json",
    "pnpm-lock.yaml",
    "prettier.config.js",
    "tsconfig.app.json",
    "tsconfig.json",
    "tsconfig.node.json",
    "vite.config.js",
    "vite.config.mjs",
    "vite.config.ts",
    "yarn.lock",
)


class SourceBundleError(RuntimeError):
    """Raised when the release source closure is incomplete or mutable."""


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _walk_error(error: OSError) -> None:
    raise SourceBundleError("Release source traversal was incomplete") from error


def _excluded(relative: Path) -> bool:
    return (
        any(part in EXCLUDED_DIRECTORIES for part in relative.parts)
        or any(part.startswith("._") for part in relative.parts)
        or relative.name == ".DS_Store"
        or relative.name == ".env"
        or relative.name.startswith(".env.")
        or relative.name.endswith(EXCLUDED_FILE_SUFFIXES)
    )


def _selected_source_files(source_root: Path) -> list[Path]:
    selected: set[Path] = set()
    for relative_root in RECURSIVE_ROOTS:
        root = source_root / relative_root
        if not root.exists():
            raise SourceBundleError(
                f"Required release source directory is missing: {relative_root}"
            )
        if root.is_symlink() or not root.is_dir():
            raise SourceBundleError(
                f"Required release source directory is unsafe: {relative_root}"
            )
        for current, directories, files in os.walk(
            root,
            topdown=True,
            followlinks=False,
            onerror=_walk_error,
        ):
            current_path = Path(current)
            kept_directories: list[str] = []
            for name in sorted(directories):
                child = current_path / name
                relative = child.relative_to(source_root)
                details = child.lstat()
                if _excluded(relative):
                    continue
                if stat.S_ISLNK(details.st_mode) or not stat.S_ISDIR(
                    details.st_mode
                ):
                    raise SourceBundleError(
                        f"Release source contains unsafe directory: {relative}"
                    )
                kept_directories.append(name)
            directories[:] = kept_directories
            for name in sorted(files):
                child = current_path / name
                relative = child.relative_to(source_root)
                if _excluded(relative):
                    continue
                details = child.lstat()
                if (
                    stat.S_ISLNK(details.st_mode)
                    or not stat.S_ISREG(details.st_mode)
                    or details.st_nlink != 1
                ):
                    raise SourceBundleError(
                        f"Release source contains unsafe file: {relative}"
                    )
                selected.add(relative)
    for name in ROOT_FILES:
        path = source_root / name
        if path.exists():
            selected.add(Path(name))
    for name in BACKEND_FILES:
        path = source_root / "backend" / name
        if path.exists():
            selected.add(Path("backend") / name)
    for name in FRONTEND_FILES:
        path = source_root / "frontend-redesign" / name
        if path.exists():
            selected.add(Path("frontend-redesign") / name)
    for relative in selected:
        path = source_root / relative
        details = path.lstat()
        if (
            stat.S_ISLNK(details.st_mode)
            or not stat.S_ISREG(details.st_mode)
            or details.st_nlink != 1
        ):
            raise SourceBundleError(
                f"Selected release source is not a single-link file: {relative}"
            )
    return sorted(selected, key=lambda value: value.as_posix())


def _command_identity(command: str, *arguments: str) -> dict[str, Any]:
    executable = shutil.which(command)
    if not executable:
        raise SourceBundleError(f"Required release tool is missing: {command}")
    path = Path(executable).resolve(strict=True)
    details = path.stat()
    if not stat.S_ISREG(details.st_mode):
        raise SourceBundleError(f"Release tool is not a regular file: {path}")
    try:
        result = subprocess.run(
            [str(path), *arguments],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise SourceBundleError(
            f"Could not identify required release tool: {command}"
        ) from error
    return {
        "path": str(path),
        "sha256": _sha256(path),
        "version": (result.stdout or result.stderr).strip(),
    }


def _closed_tree_identity(root: Path) -> dict[str, Any]:
    root = root.resolve(strict=True)
    digest = hashlib.sha256()
    entries = 0
    for current, directories, files in os.walk(
        root,
        topdown=True,
        followlinks=False,
        onerror=_walk_error,
    ):
        current_path = Path(current)
        kept: list[str] = []
        for name in sorted(directories):
            child = current_path / name
            relative = child.relative_to(root)
            details = child.lstat()
            if stat.S_ISLNK(details.st_mode):
                target = os.readlink(child)
                resolved = (child.parent / target).resolve(strict=True)
                if root not in resolved.parents and resolved != root:
                    raise SourceBundleError(
                        f"Dependency directory symlink escapes its tree: {relative}"
                    )
                digest.update(
                    f"L\0{relative.as_posix()}\0{target}\n".encode()
                )
                entries += 1
                continue
            if not stat.S_ISDIR(details.st_mode):
                raise SourceBundleError(
                    f"Dependency tree has a special entry: {relative}"
                )
            kept.append(name)
        directories[:] = kept
        for name in sorted(files):
            child = current_path / name
            relative = child.relative_to(root)
            details = child.lstat()
            if stat.S_ISLNK(details.st_mode):
                target = os.readlink(child)
                resolved = (child.parent / target).resolve(strict=True)
                if root not in resolved.parents and resolved != root:
                    resolved_details = resolved.stat()
                    if not stat.S_ISREG(resolved_details.st_mode):
                        raise SourceBundleError(
                            f"External dependency symlink is not a file: {relative}"
                        )
                    digest.update(
                        (
                            f"X\0{relative.as_posix()}\0{target}\0"
                            f"{resolved}\0{resolved_details.st_size}\0"
                            f"{_sha256(resolved)}\n"
                        ).encode()
                    )
                else:
                    digest.update(
                        f"L\0{relative.as_posix()}\0{target}\n".encode()
                    )
            elif stat.S_ISREG(details.st_mode):
                digest.update(
                    (
                        f"F\0{relative.as_posix()}\0{details.st_size}\0"
                        f"{_sha256(child)}\n"
                    ).encode()
                )
            else:
                raise SourceBundleError(
                    f"Dependency tree has a special file: {relative}"
                )
            entries += 1
    return {
        "entries": entries,
        "root": str(root),
        "sha256Tree": digest.hexdigest(),
    }


def _is_within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _homebrew_keg_root(
    python: Path,
    base_prefix: Path,
) -> Path | None:
    """Return the exact versioned Homebrew keg shared by Python and stdlib."""

    python = python.resolve(strict=True)
    base_prefix = base_prefix.resolve(strict=True)
    for candidate in python.parents:
        if candidate.parent.parent.name != "Cellar":
            continue
        if not _is_within(base_prefix, candidate):
            continue
        receipt = candidate / "INSTALL_RECEIPT.json"
        try:
            details = receipt.lstat()
        except FileNotFoundError:
            continue
        if (
            stat.S_ISLNK(details.st_mode)
            or not stat.S_ISREG(details.st_mode)
            or details.st_nlink != 1
        ):
            raise SourceBundleError(
                "Homebrew Python keg receipt is unsafe"
            )
        return candidate
    return None


def _python_identity_roots(
    python: Path,
    prefix: Path,
    base_prefix: Path,
) -> tuple[Path, ...]:
    """Bind a venv plus the narrowest complete Python installation root."""

    python = python.resolve(strict=True)
    prefix = prefix.resolve(strict=True)
    base_prefix = base_prefix.resolve(strict=True)
    keg = _homebrew_keg_root(python, base_prefix)
    if keg is None:
        roots = {prefix, base_prefix}
    else:
        roots = {
            root
            for root in (prefix,)
            if not _is_within(root, keg)
        }
        roots.add(keg)
    return tuple(sorted(roots, key=str))


def _toolchain_identity() -> dict[str, Any]:
    pg_bin = Path(
        os.environ.get(
            "CARESYNC_PG_BIN",
            "/opt/homebrew/opt/postgresql@17/bin",
        )
    )
    python = Path(sys.executable).resolve(strict=True)
    node_modules_value = os.environ.get("CARESYNC_INSTALLED_NODE_MODULES")
    if not node_modules_value:
        raise SourceBundleError(
            "CARESYNC_INSTALLED_NODE_MODULES is required for dependency binding"
        )
    postgres_tools: dict[str, Any] = {}
    for name in (
        "createdb",
        "initdb",
        "pg_basebackup",
        "pg_controldata",
        "pg_ctl",
        "pg_dump",
        "pg_isready",
        "pg_verifybackup",
        "postgres",
        "psql",
    ):
        path = (pg_bin / name).resolve(strict=True)
        if not path.is_file():
            raise SourceBundleError(f"PostgreSQL release tool is missing: {path}")
        postgres_tools[name] = {
            "path": str(path),
            "sha256": _sha256(path),
        }
    postgres_tools["psql"]["version"] = _command_identity(
        str(pg_bin / "psql"), "--version"
    )["version"]
    python_roots: dict[str, Any] = {}
    for root in _python_identity_roots(
        python,
        Path(sys.prefix),
        Path(sys.base_prefix),
    ):
        python_roots[str(root)] = _closed_tree_identity(root)
    uv_executable = shutil.which("uv")
    if not uv_executable:
        configured_uv = os.environ.get("CARESYNC_UV_EXECUTABLE")
        if configured_uv:
            uv_executable = configured_uv
    if not uv_executable:
        raise SourceBundleError("Required uv executable is missing")
    return {
        "bash": _command_identity("/bin/bash", "--version"),
        "node": _command_identity("node", "--version"),
        "nodeModules": _closed_tree_identity(Path(node_modules_value)),
        "npm": _command_identity("npm", "--version"),
        "postgres": postgres_tools,
        "python": {
            "executable": str(python),
            "sha256": _sha256(python),
            "version": sys.version,
            "importRoots": python_roots,
        },
        "uv": _command_identity(uv_executable, "--version"),
    }


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        full_sync_fd(descriptor)
    finally:
        os.close(descriptor)


def _copy_private_file(source: Path, destination: Path) -> dict[str, Any]:
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(destination.parent, 0o700)
    source_flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        source_flags |= os.O_NOFOLLOW
    source_descriptor = os.open(source, source_flags)
    destination_descriptor = os.open(
        destination,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )
    digest = hashlib.sha256()
    size = 0
    try:
        opened = os.fstat(source_descriptor)
        expected = source.lstat()
        if (
            (opened.st_dev, opened.st_ino)
            != (expected.st_dev, expected.st_ino)
            or not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
        ):
            raise SourceBundleError("Release source changed while being copied")
        while True:
            chunk = os.read(source_descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
            view = memoryview(chunk)
            while view:
                written = os.write(destination_descriptor, view)
                view = view[written:]
        os.fchmod(destination_descriptor, 0o600)
        full_sync_fd(destination_descriptor)
        finished = os.fstat(source_descriptor)
        reopened = source.lstat()
        stable_fields = (
            "st_dev",
            "st_ino",
            "st_mode",
            "st_nlink",
            "st_size",
            "st_mtime_ns",
            "st_ctime_ns",
        )
        if (
            any(
                getattr(opened, field) != getattr(finished, field)
                for field in stable_fields
            )
            or any(
                getattr(finished, field) != getattr(reopened, field)
                for field in stable_fields
            )
            or size != finished.st_size
        ):
            raise SourceBundleError(
                "Release source changed while its bytes were being copied"
            )
    finally:
        os.close(destination_descriptor)
        os.close(source_descriptor)
    return {"bytes": size, "sha256": digest.hexdigest()}


def _read_stable_source_file(path: Path) -> dict[str, Any]:
    """Hash one source file while proving its descriptor/path stayed stable."""

    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    digest = hashlib.sha256()
    size = 0
    try:
        opened = os.fstat(descriptor)
        expected = path.lstat()
        if (
            (opened.st_dev, opened.st_ino)
            != (expected.st_dev, expected.st_ino)
            or not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
        ):
            raise SourceBundleError(
                "Release source changed while its inventory was opened"
            )
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
        finished = os.fstat(descriptor)
        reopened = path.lstat()
        stable_fields = (
            "st_dev",
            "st_ino",
            "st_mode",
            "st_nlink",
            "st_size",
            "st_mtime_ns",
            "st_ctime_ns",
        )
        if (
            any(
                getattr(opened, field) != getattr(finished, field)
                for field in stable_fields
            )
            or any(
                getattr(finished, field) != getattr(reopened, field)
                for field in stable_fields
            )
            or size != finished.st_size
        ):
            raise SourceBundleError(
                "Release source changed while its inventory was read"
            )
        return {"bytes": size, "sha256": digest.hexdigest()}
    finally:
        os.close(descriptor)


def _source_inventory(
    source_root: Path,
    selected: list[Path],
) -> dict[str, dict[str, Any]]:
    return {
        relative.as_posix(): _read_stable_source_file(source_root / relative)
        for relative in selected
    }


def _publish_manifest(path: Path, payload: dict[str, Any]) -> None:
    if os.path.lexists(path):
        raise SourceBundleError("Release source manifest already exists")
    pending = path.parent / f".{path.name}.pending.{os.getpid()}"
    descriptor = os.open(
        pending,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )
    try:
        data = _canonical_json(payload) + b"\n"
        view = memoryview(data)
        while view:
            written = os.write(descriptor, view)
            view = view[written:]
        full_sync_fd(descriptor)
    finally:
        os.close(descriptor)
    try:
        os.link(pending, path, follow_symlinks=False)
        os.unlink(pending)
        _fsync_directory(path.parent)
    except OSError as error:
        raise SourceBundleError("Could not publish release source manifest") from error


def _seal_snapshot_tree(root: Path) -> dict[str, dict[str, Any]]:
    """Make every generated/copied byte private and durable, then inventory it."""

    entries: dict[str, dict[str, Any]] = {}
    for current, directories, files in os.walk(
        root,
        topdown=False,
        followlinks=False,
        onerror=_walk_error,
    ):
        current_path = Path(current)
        for name in sorted(files):
            child = current_path / name
            details = child.lstat()
            if (
                stat.S_ISLNK(details.st_mode)
                or not stat.S_ISREG(details.st_mode)
                or details.st_nlink != 1
            ):
                raise SourceBundleError(
                    f"Release snapshot contains an unsafe file: "
                    f"{child.relative_to(root)}"
                )
            os.chmod(child, 0o600)
            flags = os.O_RDONLY
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            descriptor = os.open(child, flags)
            try:
                opened = os.fstat(descriptor)
                if (
                    (opened.st_dev, opened.st_ino)
                    != (details.st_dev, details.st_ino)
                    or not stat.S_ISREG(opened.st_mode)
                ):
                    raise SourceBundleError(
                        "Release snapshot changed while being sealed"
                    )
                full_sync_fd(descriptor)
            finally:
                os.close(descriptor)
            sealed = child.stat()
            entries[child.relative_to(root).as_posix()] = {
                "bytes": sealed.st_size,
                "sha256": _sha256(child),
            }
        for name in sorted(directories):
            child = current_path / name
            details = child.lstat()
            if stat.S_ISLNK(details.st_mode) or not stat.S_ISDIR(
                details.st_mode
            ):
                raise SourceBundleError(
                    f"Release snapshot contains an unsafe directory: "
                    f"{child.relative_to(root)}"
                )
            os.chmod(child, 0o700)
            _fsync_directory(child)
        os.chmod(current_path, 0o700)
        _fsync_directory(current_path)
    return entries


def _build_frontend(
    destination: Path,
    installed_node_modules: Path,
) -> None:
    """Build once from captured source; runtime never executes mutable Vite."""

    frontend = destination / "frontend-redesign"
    dependency_link = frontend / "node_modules"
    if os.path.lexists(dependency_link):
        raise SourceBundleError("Captured frontend dependency path is occupied")
    dependency_link.symlink_to(
        installed_node_modules.resolve(strict=True),
        target_is_directory=True,
    )
    _fsync_directory(frontend)
    environment = os.environ.copy()
    environment.update(
        {
            "CI": "1",
            "NODE_ENV": "production",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    npm = shutil.which("npm")
    if not npm:
        raise SourceBundleError("Required npm executable is missing")
    dependency_identity_before = _closed_tree_identity(
        installed_node_modules
    )
    try:
        subprocess.run(
            [npm, "run", "build", "--", "--configLoader", "runner"],
            cwd=frontend,
            env=environment,
            check=True,
            timeout=900,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise SourceBundleError(
            "Captured frontend production build failed"
        ) from error
    finally:
        if dependency_link.is_symlink():
            dependency_link.unlink()
            _fsync_directory(frontend)
    dependency_identity_after = _closed_tree_identity(installed_node_modules)
    if dependency_identity_after != dependency_identity_before:
        raise SourceBundleError(
            "Frontend build mutated the installed dependency closure"
        )
    dist = frontend / "dist"
    if dist.is_symlink() or not dist.is_dir() or not (dist / "index.html").is_file():
        raise SourceBundleError(
            "Captured frontend build did not produce a safe dist/index.html"
        )


def create_snapshot(source_root: Path, destination: Path, manifest: Path) -> None:
    source_root = source_root.resolve(strict=True)
    if os.path.lexists(destination) or os.path.lexists(manifest):
        raise SourceBundleError("Release source destination must be absent")
    if destination.parent != manifest.parent:
        raise SourceBundleError("Release source and manifest must share a run")
    parent = destination.parent
    details = parent.lstat()
    if (
        not stat.S_ISDIR(details.st_mode)
        or stat.S_IMODE(details.st_mode) != 0o700
        or details.st_uid != os.geteuid()
    ):
        raise SourceBundleError("Release source parent must be private mode 0700")
    destination.mkdir(mode=0o700)
    selected_before = _selected_source_files(source_root)
    inventory_before = _source_inventory(source_root, selected_before)
    copied: dict[str, dict[str, Any]] = {}
    for relative in selected_before:
        copied[relative.as_posix()] = _copy_private_file(
            source_root / relative,
            destination / relative,
        )
    selected_after = _selected_source_files(source_root)
    inventory_after = _source_inventory(source_root, selected_after)
    if (
        selected_after != selected_before
        or inventory_before != copied
        or inventory_after != copied
    ):
        raise SourceBundleError(
            "Release source inventory changed across snapshot creation"
        )
    node_modules_value = os.environ.get("CARESYNC_INSTALLED_NODE_MODULES")
    if not node_modules_value:
        raise SourceBundleError(
            "CARESYNC_INSTALLED_NODE_MODULES is required for dependency binding"
        )
    node_modules = Path(node_modules_value).resolve(strict=True)
    _build_frontend(destination, node_modules)
    entries = _seal_snapshot_tree(destination)
    payload = {
        "files": entries,
        "format": FORMAT,
        "sourceRootBasename": source_root.name,
        "toolchain": _toolchain_identity(),
    }
    _publish_manifest(manifest, payload)
    verify_snapshot(destination, manifest)


def _read_manifest(path: Path) -> dict[str, Any]:
    details = path.lstat()
    if (
        not stat.S_ISREG(details.st_mode)
        or stat.S_IMODE(details.st_mode) != 0o600
        or details.st_uid != os.geteuid()
        or details.st_nlink != 1
    ):
        raise SourceBundleError("Release source manifest is not private")
    try:
        value = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as error:
        raise SourceBundleError("Release source manifest is unreadable") from error
    if (
        not isinstance(value, dict)
        or value.get("format") != FORMAT
        or not isinstance(value.get("files"), dict)
        or not isinstance(value.get("toolchain"), dict)
    ):
        raise SourceBundleError("Release source manifest has an invalid format")
    return value


def verify_snapshot(destination: Path, manifest: Path) -> None:
    payload = _read_manifest(manifest)
    details = destination.lstat()
    if (
        not stat.S_ISDIR(details.st_mode)
        or stat.S_IMODE(details.st_mode) != 0o700
        or details.st_uid != os.geteuid()
    ):
        raise SourceBundleError("Release source root is not private mode 0700")
    actual: dict[str, dict[str, Any]] = {}
    for current, directories, files in os.walk(
        destination,
        topdown=True,
        followlinks=False,
        onerror=_walk_error,
    ):
        current_path = Path(current)
        for name in directories:
            child = current_path / name
            child_details = child.lstat()
            if (
                stat.S_ISLNK(child_details.st_mode)
                or not stat.S_ISDIR(child_details.st_mode)
                or stat.S_IMODE(child_details.st_mode) != 0o700
                or child_details.st_uid != os.geteuid()
            ):
                raise SourceBundleError("Release source has an unsafe directory")
        for name in files:
            child = current_path / name
            child_details = child.lstat()
            if (
                stat.S_ISLNK(child_details.st_mode)
                or not stat.S_ISREG(child_details.st_mode)
                or stat.S_IMODE(child_details.st_mode) != 0o600
                or child_details.st_uid != os.geteuid()
                or child_details.st_nlink != 1
            ):
                raise SourceBundleError("Release source has an unsafe file")
            relative = child.relative_to(destination).as_posix()
            actual[relative] = {
                "bytes": child_details.st_size,
                "sha256": _sha256(child),
            }
    if actual != payload["files"]:
        raise SourceBundleError("Release source closed inventory has drifted")
    if _toolchain_identity() != payload["toolchain"]:
        raise SourceBundleError("Release source toolchain identity has drifted")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create")
    create.add_argument("--source-root", type=Path, required=True)
    create.add_argument("--destination", type=Path, required=True)
    create.add_argument("--manifest", type=Path, required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("--destination", type=Path, required=True)
    verify.add_argument("--manifest", type=Path, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        if args.command == "create":
            create_snapshot(args.source_root, args.destination, args.manifest)
        elif args.command == "verify":
            verify_snapshot(args.destination, args.manifest)
        else:
            raise SourceBundleError("Unsupported release source command")
    except (OSError, SourceBundleError) as error:
        print(f"Release source error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
