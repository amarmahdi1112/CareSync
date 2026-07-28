"""Filesystem-topology gates for prepare, commit, and physical rollback."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_LIBRARY = PROJECT_ROOT / "scripts" / "lib" / "basic-runtime.sh"
RELEASE_SCRIPT = PROJECT_ROOT / "scripts" / "basic-release.sh"


def _private_directory(path: Path) -> Path:
    path.mkdir(mode=0o700)
    path.chmod(0o700)
    return path


def test_topology_helper_checks_every_release_anchor(tmp_path: Path) -> None:
    runtime = _private_directory(tmp_path / "runtime")
    _private_directory(runtime / "postgres-data")
    releases = _private_directory(runtime / "releases")
    run = _private_directory(releases / "20260726T000000Z-1")
    quarantine = _private_directory(runtime / "quarantine")
    physical = run / "physical-postgres"
    probe = """
set -euo pipefail
ROOT="$1"
export CARESYNC_BASIC_RUNTIME="$2"
source "$3"
calls=()
basic_require_same_apfs_device() {
  calls+=("$1|$2")
}
basic_require_release_apfs_topology "$4" "$5"
[[ "${#calls[@]}" == "4" ]]
[[ "${calls[0]}" == "$2|$2/postgres-data" ]]
[[ "${calls[1]}" == "$2|$2/releases" ]]
[[ "${calls[2]}" == "$2|$(dirname "$4")" ]]
[[ "${calls[3]}" == "$2|$5" ]]
"""
    subprocess.run(
        [
            "/bin/bash",
            "-c",
            probe,
            "bash",
            str(PROJECT_ROOT),
            str(runtime),
            str(RUNTIME_LIBRARY),
            str(physical),
            str(quarantine),
        ],
        check=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )


def test_topology_preflight_precedes_every_irreversible_boundary() -> None:
    source = RELEASE_SCRIPT.read_text(encoding="utf-8")
    prepare = source[
        source.index("prepare_release()") : source.index("commit_release()")
    ]
    commit = source[
        source.index("commit_release()") : source.index("resume_release_0039()")
    ]
    rollback = source[
        source.index("rollback_release()") : source.index("load_release_run()")
    ]

    prepare_topology = prepare.index("basic_require_release_apfs_topology")
    assert prepare_topology < prepare.index("create_fence")
    assert prepare_topology < prepare.index("basic_release_contract.py prepare")

    commit_topology = commit.index("basic_require_release_apfs_topology")
    assert commit_topology < commit.index("create_commit_attempt_intent")
    assert commit_topology < commit.index("alembic upgrade")

    rollback_topologies = [
        position
        for position in range(len(rollback))
        if rollback.startswith("basic_require_release_apfs_topology", position)
    ]
    assert len(rollback_topologies) >= 4
    assert rollback_topologies[0] < rollback.index("write_rollback_context")
    first_rename = rollback.index("atomic_rollback_rename_no_replace")
    second_rename = rollback.index(
        "atomic_rollback_rename_no_replace",
        first_rename + 1,
    )
    assert any(position < first_rename for position in rollback_topologies)
    assert any(
        first_rename < position < second_rename
        for position in rollback_topologies
    )
