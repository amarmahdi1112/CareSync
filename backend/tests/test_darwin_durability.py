"""Ordering and fail-closed tests for release durability barriers."""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

from scripts import darwin_durability


def test_darwin_full_sync_orders_fsync_before_fullfsync(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, int, int | None]] = []
    monkeypatch.setattr(darwin_durability.sys, "platform", "darwin")
    monkeypatch.setattr(
        darwin_durability.os,
        "fsync",
        lambda descriptor: calls.append(("fsync", descriptor, None)),
    )
    monkeypatch.setattr(
        darwin_durability.fcntl,
        "fcntl",
        lambda descriptor, command: (
            calls.append(("fcntl", descriptor, command)),
            0,
        )[1],
    )

    darwin_durability.full_sync_fd(17)

    assert calls == [
        ("fsync", 17, None),
        ("fcntl", 17, darwin_durability.DARWIN_F_FULLFSYNC),
    ]


def test_darwin_full_sync_propagates_fsync_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(darwin_durability.sys, "platform", "darwin")

    def fail_fsync(_descriptor: int) -> None:
        raise OSError("fsync failed")

    monkeypatch.setattr(darwin_durability.os, "fsync", fail_fsync)
    with pytest.raises(OSError, match="fsync failed"):
        darwin_durability.full_sync_fd(18)


def test_darwin_full_sync_propagates_fullfsync_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(darwin_durability.sys, "platform", "darwin")
    monkeypatch.setattr(darwin_durability.os, "fsync", lambda _descriptor: None)

    def fail_full_sync(_descriptor: int, _command: int) -> int:
        raise OSError("full sync failed")

    monkeypatch.setattr(darwin_durability.fcntl, "fcntl", fail_full_sync)
    with pytest.raises(OSError, match="full sync failed"):
        darwin_durability.full_sync_fd(19)


@pytest.mark.skipif(sys.platform != "darwin", reason="Darwin APFS smoke only")
def test_full_sync_smoke_on_apfs(tmp_path) -> None:
    device = subprocess.run(
        ["/bin/df", "-P", str(tmp_path)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()[1].split()[0]
    try:
        disk = subprocess.run(
            ["/usr/sbin/diskutil", "info", "-plist", device],
            check=True,
            capture_output=True,
        )
        filesystem = subprocess.run(
            [
                "/usr/bin/plutil",
                "-extract",
                "FilesystemType",
                "raw",
                "-o",
                "-",
                "-",
            ],
            input=disk.stdout,
            check=True,
            capture_output=True,
        ).stdout.decode("utf-8").strip()
    except (OSError, subprocess.CalledProcessError) as error:
        pytest.skip(f"APFS attestation is unavailable: {error}")
    if filesystem != "apfs":
        pytest.skip(f"temporary test root is {filesystem}, not APFS")

    payload = tmp_path / "barrier.bin"
    file_descriptor = os.open(
        payload,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )
    try:
        os.write(file_descriptor, b"caresync-durability-smoke")
        darwin_durability.full_sync_fd(file_descriptor)
    finally:
        os.close(file_descriptor)

    directory_descriptor = os.open(
        tmp_path,
        os.O_RDONLY | os.O_DIRECTORY,
    )
    try:
        darwin_durability.full_sync_fd(directory_descriptor)
    finally:
        os.close(directory_descriptor)
