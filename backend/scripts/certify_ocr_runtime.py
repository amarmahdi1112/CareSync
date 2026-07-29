#!/usr/bin/env python3
"""Certify the isolated Linux OCR environment against its hashed release lock."""

from __future__ import annotations

import re
import sys
from importlib import import_module
from importlib.metadata import distributions
from pathlib import Path
from platform import machine

LOCK_ENTRY = re.compile(
    r"^(?P<name>[A-Za-z0-9_.-]+(?:\[[A-Za-z0-9_,.-]+\])?)"
    r"==(?P<version>[^\s]+) --hash=sha256:(?P<digest>[0-9a-f]{64})$"
)


def normalize_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).casefold()


def read_lock(path: Path) -> dict[str, str]:
    expected: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = LOCK_ENTRY.fullmatch(line)
        if match is None:
            raise SystemExit(f"OCR lock entry is invalid: {line!r}")
        name = normalize_name(match.group("name").split("[", 1)[0])
        if name in expected:
            raise SystemExit(f"OCR lock contains duplicate distribution {name!r}")
        expected[name] = match.group("version")
    if not expected:
        raise SystemExit("OCR lock is empty")
    return expected


def installed_versions() -> dict[str, str]:
    installed: dict[str, str] = {}
    for distribution in distributions():
        raw_name = distribution.metadata.get("Name")
        if not raw_name:
            raise SystemExit("OCR environment contains an unnamed distribution")
        name = normalize_name(raw_name)
        if name in installed:
            raise SystemExit(f"OCR environment contains duplicate distribution {name!r}")
        installed[name] = distribution.version
    # pip is the CPython venv installer, not an OCR runtime dependency.
    installed.pop("pip", None)
    return installed


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: certify_ocr_runtime.py LOCK_FILE")
    if (
        sys.platform != "linux"
        or sys.version_info[:2] != (3, 12)
        or machine() != "x86_64"
    ):
        raise SystemExit("OCR runtime must use Linux x86_64 CPython 3.12")

    expected = read_lock(Path(sys.argv[1]))
    actual = installed_versions()
    if actual != expected:
        missing = sorted(expected.keys() - actual.keys())
        unexpected = sorted(actual.keys() - expected.keys())
        changed = sorted(
            name
            for name in expected.keys() & actual.keys()
            if expected[name] != actual[name]
        )
        raise SystemExit(
            "OCR distribution inventory differs from the release lock: "
            f"missing={missing!r} unexpected={unexpected!r} changed={changed!r}"
        )

    cv2 = import_module("cv2")
    for required_module in ("fitz", "paddle", "paddleocr"):
        import_module(required_module)
    if cv2.__version__ != "4.10.0":
        raise SystemExit(f"OpenCV runtime version differs: {cv2.__version__!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
