"""Portable filesystem hardening tests for disposable-restore receipts."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

import scripts.restore_database as restore_database
from scripts.restore_database import RestoreContractError, write_private_restore_receipt


def _private_directory(path: Path) -> Path:
    path.mkdir(mode=0o700)
    path.chmod(0o700)
    return path


def test_restore_receipt_creates_private_owned_single_link_json(tmp_path: Path) -> None:
    receipt = tmp_path / "nested" / "private" / "restore.json"
    payload = {"result": "verified", "counts": {"families": 2, "children": 3}}

    write_private_restore_receipt(receipt, payload)

    parent_details = receipt.parent.stat(follow_symlinks=False)
    receipt_details = receipt.stat(follow_symlinks=False)
    assert stat.S_ISDIR(parent_details.st_mode)
    assert stat.S_IMODE(parent_details.st_mode) == 0o700
    assert parent_details.st_uid == os.geteuid()
    assert stat.S_ISREG(receipt_details.st_mode)
    assert stat.S_IMODE(receipt_details.st_mode) == 0o600
    assert receipt_details.st_uid == os.geteuid()
    assert receipt_details.st_nlink == 1
    assert json.loads(receipt.read_text(encoding="utf-8")) == payload


def test_restore_receipt_refuses_to_clobber_existing_regular_file(tmp_path: Path) -> None:
    parent = _private_directory(tmp_path / "private")
    receipt = parent / "restore.json"
    original = b"operator-owned existing receipt\n"
    receipt.write_bytes(original)
    receipt.chmod(0o600)

    with pytest.raises(RestoreContractError, match="Refusing to replace"):
        write_private_restore_receipt(receipt, {"result": "replacement"})

    assert receipt.read_bytes() == original
    assert stat.S_IMODE(receipt.stat(follow_symlinks=False).st_mode) == 0o600


def test_restore_receipt_refuses_output_symlink_without_touching_target(tmp_path: Path) -> None:
    parent = _private_directory(tmp_path / "private")
    target = tmp_path / "operator-file.json"
    original = b"do not replace through a link\n"
    target.write_bytes(original)
    receipt = parent / "restore.json"
    receipt.symlink_to(target)

    with pytest.raises(RestoreContractError, match="Refusing to replace"):
        write_private_restore_receipt(receipt, {"result": "replacement"})

    assert receipt.is_symlink()
    assert target.read_bytes() == original


def test_restore_receipt_rejects_existing_parent_with_unsafe_mode(tmp_path: Path) -> None:
    parent = tmp_path / "shared"
    parent.mkdir(mode=0o755)
    parent.chmod(0o755)

    with pytest.raises(RestoreContractError, match="owner-controlled mode 0700"):
        write_private_restore_receipt(parent / "restore.json", {"result": "unsafe"})

    assert not (parent / "restore.json").exists()


def test_restore_receipt_rejects_symlinked_intermediate_component(tmp_path: Path) -> None:
    real_parent = _private_directory(tmp_path / "real")
    linked_parent = tmp_path / "linked"
    linked_parent.symlink_to(real_parent, target_is_directory=True)

    with pytest.raises(RestoreContractError, match="symbolic link"):
        write_private_restore_receipt(
            linked_parent / "nested" / "restore.json",
            {"result": "unsafe"},
        )

    assert not (real_parent / "nested").exists()


def test_restore_receipt_detects_hard_link_race_and_removes_requested_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent = _private_directory(tmp_path / "private")
    receipt = parent / "restore.json"
    competing_link = parent / "raced-link.json"
    real_stat = os.stat
    injected = False

    def stat_after_injecting_link(
        path: os.PathLike[str] | str,
        *,
        dir_fd: int | None = None,
        follow_symlinks: bool = True,
    ) -> os.stat_result:
        nonlocal injected
        if path == receipt.name and dir_fd is not None and not follow_symlinks and not injected:
            os.link(receipt, competing_link)
            injected = True
        return real_stat(path, dir_fd=dir_fd, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(restore_database.os, "stat", stat_after_injecting_link)

    with pytest.raises(RestoreContractError, match="single-link file"):
        write_private_restore_receipt(receipt, {"result": "must-fail-closed"})

    assert injected is True
    assert not receipt.exists()
    assert competing_link.exists()
    assert competing_link.stat(follow_symlinks=False).st_nlink == 1


def test_restore_receipt_cleanup_preserves_replacement_winner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent = _private_directory(tmp_path / "private")
    receipt = parent / "restore.json"
    displaced = parent / "displaced-created-receipt.json"
    winner = b"operator-owned winner\n"
    real_stat = os.stat
    injected = False

    def stat_after_replacing_created_name(
        path: os.PathLike[str] | str,
        *,
        dir_fd: int | None = None,
        follow_symlinks: bool = True,
    ) -> os.stat_result:
        nonlocal injected
        if path == receipt.name and dir_fd is not None and not follow_symlinks and not injected:
            receipt.rename(displaced)
            receipt.write_bytes(winner)
            receipt.chmod(0o600)
            injected = True
        return real_stat(path, dir_fd=dir_fd, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(
        restore_database.os,
        "stat",
        stat_after_replacing_created_name,
    )

    with pytest.raises(RestoreContractError, match="single-link file"):
        write_private_restore_receipt(receipt, {"result": "must-fail-closed"})

    assert injected is True
    assert receipt.read_bytes() == winner
    assert displaced.is_file()


def test_restore_receipt_refuses_success_when_new_parent_cannot_be_synced(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt = tmp_path / "new-private-parent" / "nested" / "restore.json"

    def fail_sync(_: int) -> None:
        raise OSError("synthetic sync failure")

    monkeypatch.setattr(restore_database.os, "fsync", fail_sync)

    with pytest.raises(RestoreContractError, match="durably created"):
        write_private_restore_receipt(receipt, {"result": "must-not-exist"})

    assert not receipt.exists()
