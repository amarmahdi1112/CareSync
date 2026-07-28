"""Durability ordering for managed runtime directories."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from scripts import basic_release_contract


def _private_directory(path: Path) -> Path:
    path.mkdir(mode=0o700)
    path.chmod(0o700)
    return path


def _descriptor_identity(descriptor: int) -> tuple[int, int]:
    details = os.fstat(descriptor)
    return details.st_dev, details.st_ino


def test_new_runtime_child_is_barriered_before_its_parent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _private_directory(tmp_path / "runtime")
    child = runtime / "pids"
    barriers: list[tuple[int, int]] = []

    monkeypatch.setattr(
        basic_release_contract,
        "full_sync_fd",
        lambda descriptor: barriers.append(_descriptor_identity(descriptor)),
    )

    basic_release_contract.ensure_private_directory(child)

    assert stat.S_IMODE(child.stat().st_mode) == 0o700
    assert barriers == [
        (runtime.stat().st_dev, runtime.stat().st_ino),
        (tmp_path.stat().st_dev, tmp_path.stat().st_ino),
        (child.stat().st_dev, child.stat().st_ino),
        (runtime.stat().st_dev, runtime.stat().st_ino),
    ]


@pytest.mark.parametrize("failed_barrier", ["child", "parent"])
def test_runtime_directory_barrier_failure_propagates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failed_barrier: str,
) -> None:
    runtime = _private_directory(tmp_path / f"runtime-{failed_barrier}")
    child = runtime / "pids"
    barriers: list[tuple[int, int]] = []
    # The existing private runtime and its parent are re-barriered first.
    # The newly-created child and its parent are the third and fourth calls.
    failure_index = 2 if failed_barrier == "child" else 3

    def fail_selected_barrier(descriptor: int) -> None:
        barriers.append(_descriptor_identity(descriptor))
        if len(barriers) - 1 == failure_index:
            raise OSError(f"{failed_barrier} durability barrier failed")

    monkeypatch.setattr(
        basic_release_contract,
        "full_sync_fd",
        fail_selected_barrier,
    )

    with pytest.raises(
        OSError,
        match=rf"{failed_barrier} durability barrier failed",
    ):
        basic_release_contract.ensure_private_directory(child)

    expected = [
        (runtime.stat().st_dev, runtime.stat().st_ino),
        (tmp_path.stat().st_dev, tmp_path.stat().st_ino),
        (child.stat().st_dev, child.stat().st_ino),
        (runtime.stat().st_dev, runtime.stat().st_ino),
    ]
    assert barriers == expected[: failure_index + 1]

    retry_barriers: list[tuple[int, int]] = []
    monkeypatch.setattr(
        basic_release_contract,
        "full_sync_fd",
        lambda descriptor: retry_barriers.append(
            _descriptor_identity(descriptor)
        ),
    )

    basic_release_contract.ensure_private_directory(child)

    assert retry_barriers == [
        (child.stat().st_dev, child.stat().st_ino),
        (runtime.stat().st_dev, runtime.stat().st_ino),
    ]


def test_nested_retry_rebarriers_partial_existing_ancestor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _private_directory(tmp_path / "runtime-nested")
    outer = runtime / "releases"
    child = outer / "run"
    first_barriers: list[tuple[int, int]] = []

    def fail_outer_parent(descriptor: int) -> None:
        first_barriers.append(_descriptor_identity(descriptor))
        if len(first_barriers) == 4:
            raise OSError("outer parent durability barrier failed")

    monkeypatch.setattr(
        basic_release_contract,
        "full_sync_fd",
        fail_outer_parent,
    )
    with pytest.raises(OSError, match="outer parent durability barrier failed"):
        basic_release_contract.ensure_private_directory(child)

    assert outer.is_dir()
    assert not child.exists()
    assert first_barriers == [
        (runtime.stat().st_dev, runtime.stat().st_ino),
        (tmp_path.stat().st_dev, tmp_path.stat().st_ino),
        (outer.stat().st_dev, outer.stat().st_ino),
        (runtime.stat().st_dev, runtime.stat().st_ino),
    ]

    retry_barriers: list[tuple[int, int]] = []
    monkeypatch.setattr(
        basic_release_contract,
        "full_sync_fd",
        lambda descriptor: retry_barriers.append(
            _descriptor_identity(descriptor)
        ),
    )

    basic_release_contract.ensure_private_directory(child)

    assert retry_barriers == [
        (outer.stat().st_dev, outer.stat().st_ino),
        (runtime.stat().st_dev, runtime.stat().st_ino),
        (child.stat().st_dev, child.stat().st_ino),
        (outer.stat().st_dev, outer.stat().st_ino),
    ]


def test_runtime_layout_is_durable_before_any_launch_evidence() -> None:
    repository = Path(__file__).resolve().parents[2]
    runtime_source = (repository / "scripts/lib/basic-runtime.sh").read_text()
    launcher_source = (repository / "scripts/start-basic.sh").read_text()

    layout_start = runtime_source.index("basic_require_runtime_layout() {")
    layout_end = runtime_source.index("\n}\n", layout_start)
    layout = runtime_source[layout_start:layout_end]
    assert 'basic_durable_ensure_private_runtime_directory "$RUNTIME_DIR"' in layout
    assert 'basic_durable_ensure_private_runtime_directory "$directory"' in layout
    assert 'mkdir -m 700 "$RUNTIME_DIR"' not in layout
    assert 'mkdir -m 700 "$directory"' not in layout

    layout_call = launcher_source.index("basic_require_runtime_layout")
    first_launch_intent = launcher_source.index("basic_prepare_managed_launch")
    assert layout_call < first_launch_intent
    assert (
        'basic_durable_ensure_private_runtime_directory "$private_vault"'
        in launcher_source
    )
    assert 'mkdir -m 700 "$private_vault"' not in launcher_source
