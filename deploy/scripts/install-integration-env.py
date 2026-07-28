#!/usr/bin/env python3
"""Install an owner-private allowlisted integration environment from stdin."""

from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

TARGET = Path("/etc/caresync/integrations.env")
ALLOWED = {
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_MODEL",
    "GEMINI_API_KEY",
    "GEMINI_MODEL",
    "EXPO_PUSH_ACCESS_TOKEN",
}
KEY = re.compile(r"^[A-Z][A-Z0-9_]*$")


def main() -> int:
    if os.geteuid() != 0:
        raise SystemExit("root is required")
    raw = sys.stdin.buffer.read(64 * 1024 + 1)
    if len(raw) > 64 * 1024 or b"\x00" in raw:
        raise SystemExit("integration environment is invalid")
    text = raw.decode("utf-8")
    values: dict[str, str] = {}
    for line in text.splitlines():
        if not line or line.lstrip().startswith("#"):
            continue
        name, separator, value = line.partition("=")
        if not separator or not KEY.fullmatch(name) or name not in ALLOWED:
            raise SystemExit("integration environment contains an unsupported key")
        if "\n" in value or "\r" in value:
            raise SystemExit("integration environment contains an invalid value")
        values[name] = value
    payload = "".join(f"{name}={value}\n" for name, value in sorted(values.items()))
    TARGET.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".integrations.", dir=TARGET.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, TARGET)
        directory = os.open(TARGET.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
