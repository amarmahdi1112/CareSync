"""Strict local durability barriers for CareSync release state.

On Darwin, ``fsync(2)`` does not guarantee that a drive has drained its write
cache. CareSync release state crosses irreversible filesystem phases, so every
state-critical file or directory descriptor is first fsync'd and then sent
through ``F_FULLFSYNC``. Failure is deliberately propagated to the caller.
"""

from __future__ import annotations

import fcntl
import os
import sys

DARWIN_F_FULLFSYNC = 51


def full_sync_fd(descriptor: int) -> None:
    """Flush one descriptor and, on Darwin, drain its device write queue."""

    os.fsync(descriptor)
    if sys.platform != "darwin":
        return
    command = getattr(fcntl, "F_FULLFSYNC", DARWIN_F_FULLFSYNC)
    result = fcntl.fcntl(descriptor, command)
    if result != 0:
        raise OSError(
            f"F_FULLFSYNC returned an unexpected result: {result}"
        )
