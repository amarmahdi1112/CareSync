"""Durable, fail-closed handoff for detached CareSync services.

The parent publishes an intent before ``fork``, publishes the child's PID,
and only then publishes a PID-bound gate.  The child cannot execute the
service until both records match.  PID-bound intent/gate records remain
durable for the full service lifetime; interrupted launches and ordinary
stops reconcile that evidence before legacy PID handling.
"""

from __future__ import annotations

import argparse
import os
import signal
import stat
import subprocess
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

if __package__:
    from .darwin_durability import full_sync_fd
else:
    from darwin_durability import full_sync_fd


_SERVICES = {"backend", "frontend", "push-worker"}
_HEX = frozenset("0123456789abcdef")


class LaunchGateError(RuntimeError):
    """Raised when managed-launch evidence is unsafe or inconsistent."""


@dataclass(frozen=True)
class PrivateRecord:
    """One descriptor-verified private record."""

    values: dict[str, str]
    device: int
    inode: int


@dataclass(frozen=True)
class LaunchEvidence:
    """Exact launch intent and optional release gate."""

    intent: PrivateRecord
    gate: PrivateRecord | None
    nonce: str


def _absolute_lexical(path: Path) -> Path:
    value = Path(os.path.abspath(path))
    if not value.is_absolute():
        raise LaunchGateError("Managed launch paths must be absolute")
    return value


def _open_private_parent(paths: Sequence[Path]) -> tuple[Path, int]:
    if not paths:
        raise LaunchGateError("Managed launch evidence paths are missing")
    absolute = [_absolute_lexical(path) for path in paths]
    parent = absolute[0].parent
    if any(path.parent != parent for path in absolute[1:]):
        raise LaunchGateError("Managed launch records must share one directory")
    try:
        if parent.resolve(strict=True) != parent:
            raise LaunchGateError(
                "Managed launch directory contains a symbolic link"
            )
        details = parent.lstat()
    except OSError as error:
        raise LaunchGateError(
            "Managed launch directory is unavailable"
        ) from error
    if (
        not stat.S_ISDIR(details.st_mode)
        or stat.S_IMODE(details.st_mode) != 0o700
        or details.st_uid != os.geteuid()
    ):
        raise LaunchGateError(
            "Managed launch directory must be owner-controlled mode 0700"
        )
    flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    descriptor = os.open(parent, flags)
    opened = os.fstat(descriptor)
    if (opened.st_dev, opened.st_ino) != (details.st_dev, details.st_ino):
        os.close(descriptor)
        raise LaunchGateError("Managed launch directory changed while opened")
    return parent, descriptor


def _record_exists(name: str, parent_descriptor: int) -> bool:
    try:
        os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return False
    return True


def _private_lines(
    path: Path,
    *,
    count: int,
    parent_descriptor: int,
) -> PrivateRecord:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    try:
        descriptor = os.open(path.name, flags, dir_fd=parent_descriptor)
    except OSError as error:
        raise LaunchGateError(
            f"Managed launch evidence is unavailable: {path}"
        ) from error
    try:
        details = os.fstat(descriptor)
        if (
            not stat.S_ISREG(details.st_mode)
            or stat.S_IMODE(details.st_mode) != 0o600
            or details.st_uid != os.geteuid()
            or details.st_nlink != 1
        ):
            raise LaunchGateError(
                f"Managed launch evidence is unsafe: {path}"
            )
        chunks: list[bytes] = []
        size = 0
        while True:
            chunk = os.read(descriptor, 4096)
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
            if size > 16_384:
                raise LaunchGateError(
                    f"Managed launch evidence is oversized: {path}"
                )
    finally:
        os.close(descriptor)
    try:
        lines = b"".join(chunks).decode("utf-8").splitlines()
    except UnicodeDecodeError as error:
        raise LaunchGateError(
            f"Managed launch evidence is not UTF-8: {path}"
        ) from error
    if len(lines) != count:
        raise LaunchGateError(
            f"Managed launch evidence has wrong shape: {path}"
        )
    values: dict[str, str] = {}
    for line in lines:
        key, separator, value = line.partition("=")
        if not separator or not key or not value or key in values:
            raise LaunchGateError(
                f"Managed launch evidence has invalid fields: {path}"
            )
        values[key] = value
    return PrivateRecord(
        values=values,
        device=details.st_dev,
        inode=details.st_ino,
    )


def _validate_nonce(nonce: str) -> None:
    if len(nonce) != 64 or any(character not in _HEX for character in nonce):
        raise LaunchGateError("Managed launch nonce is invalid")


def _read_launch_evidence(
    *,
    intent: Path,
    gate: Path,
    service: str,
    expected_cwd: Path,
    signature: str,
    parent_descriptor: int,
    gate_required: bool,
) -> LaunchEvidence:
    intent_record = _private_lines(
        intent,
        count=6,
        parent_descriptor=parent_descriptor,
    )
    intent_values = intent_record.values
    nonce = intent_values.get("nonce", "")
    _validate_nonce(nonce)
    expected_intent = {
        "status": "managed_launch_pending",
        "service": service,
        "nonce": nonce,
        "parent_pid": intent_values.get("parent_pid", ""),
        "expected_cwd": str(expected_cwd),
        "signature": signature,
    }
    if (
        intent_values != expected_intent
        or not intent_values["parent_pid"].isdigit()
        or int(intent_values["parent_pid"]) <= 1
    ):
        raise LaunchGateError("Managed launch intent does not match service")

    gate_record: PrivateRecord | None = None
    if _record_exists(gate.name, parent_descriptor):
        gate_record = _private_lines(
            gate,
            count=4,
            parent_descriptor=parent_descriptor,
        )
        gate_values = gate_record.values
        if (
            gate_values
            != {
                "status": "managed_launch_released",
                "service": service,
                "nonce": nonce,
                "pid": gate_values.get("pid", ""),
            }
            or not gate_values["pid"].isdigit()
            or int(gate_values["pid"]) <= 1
        ):
            raise LaunchGateError("Managed launch gate does not match intent")
    elif gate_required:
        raise LaunchGateError("Managed launch gate is missing")
    return LaunchEvidence(intent=intent_record, gate=gate_record, nonce=nonce)


def _read_decimal_pid(path: Path, parent_descriptor: int) -> PrivateRecord:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    try:
        descriptor = os.open(path.name, flags, dir_fd=parent_descriptor)
    except OSError as error:
        raise LaunchGateError("Managed PID record is unavailable") from error
    try:
        details = os.fstat(descriptor)
        payload = os.read(descriptor, 64)
        if os.read(descriptor, 1):
            raise LaunchGateError("Managed PID record is oversized")
    finally:
        os.close(descriptor)
    try:
        value = payload.decode("ascii").strip()
    except UnicodeDecodeError as error:
        raise LaunchGateError("Managed PID record is not ASCII") from error
    if (
        not stat.S_ISREG(details.st_mode)
        or stat.S_IMODE(details.st_mode) != 0o600
        or details.st_uid != os.geteuid()
        or details.st_nlink != 1
        or not value.isdigit()
        or int(value) <= 1
    ):
        raise LaunchGateError("Managed PID record is invalid")
    return PrivateRecord(
        values={"pid": value},
        device=details.st_dev,
        inode=details.st_ino,
    )


def _remove_records(
    records: Sequence[tuple[Path, PrivateRecord]],
    *,
    parent_descriptor: int,
) -> None:
    for path, record in records:
        try:
            current = os.stat(
                path.name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError as error:
            raise LaunchGateError(
                f"Managed launch record vanished before removal: {path}"
            ) from error
        if (current.st_dev, current.st_ino) != (record.device, record.inode):
            raise LaunchGateError(
                f"Managed launch record changed before removal: {path}"
            )
        os.unlink(path.name, dir_fd=parent_descriptor)
        # Publish each monotonic removal before advancing to the next record.
        # Reconciliation removes PID, then gate, then intent, so every
        # power-loss prefix remains an explicitly recoverable stopped state.
        full_sync_fd(parent_descriptor)


def _wait_for_gate(
    *,
    intent: Path,
    gate: Path,
    pid_file: Path,
    service: str,
    nonce: str,
    expected_cwd: Path,
    signature: str,
    timeout_seconds: float,
) -> None:
    _, parent_descriptor = _open_private_parent((intent, gate, pid_file))
    try:
        initial = _read_launch_evidence(
            intent=intent,
            gate=gate,
            service=service,
            expected_cwd=expected_cwd,
            signature=signature,
            parent_descriptor=parent_descriptor,
            gate_required=False,
        )
        if initial.nonce != nonce:
            raise LaunchGateError(
                "Managed launch intent nonce does not match this child"
            )
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if _record_exists(gate.name, parent_descriptor):
                current = _read_launch_evidence(
                    intent=intent,
                    gate=gate,
                    service=service,
                    expected_cwd=expected_cwd,
                    signature=signature,
                    parent_descriptor=parent_descriptor,
                    gate_required=True,
                )
                if (
                    current.nonce != nonce
                    or current.intent.values != initial.intent.values
                    or current.gate is None
                    or current.gate.values["pid"] != str(os.getpid())
                ):
                    raise LaunchGateError(
                        "Managed launch gate does not match this child"
                    )
                pid_record = _read_decimal_pid(pid_file, parent_descriptor)
                if pid_record.values["pid"] != str(os.getpid()):
                    raise LaunchGateError(
                        "Managed launch PID record does not match this child"
                    )
                return
            if not _record_exists(intent.name, parent_descriptor):
                raise LaunchGateError(
                    "Managed launch intent vanished before gate"
                )
            time.sleep(0.05)
    finally:
        os.close(parent_descriptor)
    raise LaunchGateError("Managed launch gate timed out")


def _process_rows() -> list[tuple[int, str]]:
    completed = subprocess.run(
        ["/bin/ps", "-ax", "-ww", "-o", "pid=,command="],
        check=True,
        capture_output=True,
        text=True,
    )
    rows: list[tuple[int, str]] = []
    for line in completed.stdout.splitlines():
        stripped = line.strip()
        pid_text, separator, command = stripped.partition(" ")
        if not separator or not pid_text.isdigit() or not command.strip():
            raise LaunchGateError("Process inspection returned invalid output")
        rows.append((int(pid_text), command.strip()))
    return rows


def _process_cwd(pid: int) -> Path:
    completed = subprocess.run(
        ["/usr/sbin/lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"],
        check=True,
        capture_output=True,
        text=True,
    )
    values = [
        line[1:]
        for line in completed.stdout.splitlines()
        if line.startswith("n")
    ]
    if len(values) != 1:
        raise LaunchGateError("Managed process cwd is ambiguous")
    return Path(values[0]).resolve(strict=True)


def _process_is_present(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError as error:
        raise LaunchGateError("Managed process ownership is ambiguous") from error
    completed = subprocess.run(
        ["/bin/ps", "-p", str(pid), "-o", "state="],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode == 1 and not completed.stdout:
        return False
    if completed.returncode != 0:
        raise LaunchGateError("Managed process state is ambiguous")
    return not completed.stdout.strip().startswith("Z")


def _is_gate_wrapper(
    command: str,
    *,
    intent: Path,
    gate: Path,
    service: str,
    nonce: str | None,
) -> bool:
    padded = f" {command} "
    required = (
        "gated_service_exec.py",
        " hold ",
        str(intent),
        str(gate),
        f"--service {service}",
    )
    if not all(value in padded for value in required):
        return False
    return nonce is None or f"--nonce {nonce}" in padded


def _command_for_pid(pid: int) -> str | None:
    completed = subprocess.run(
        ["/bin/ps", "-p", str(pid), "-ww", "-o", "command="],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode == 1 and not completed.stdout:
        return None
    if completed.returncode != 0 or not completed.stdout.strip():
        raise LaunchGateError("Managed process command is ambiguous")
    return completed.stdout.strip()


def _terminate_exact_processes(
    allowed_commands: dict[int, tuple[str, ...]],
    *,
    expected_cwd: Path,
) -> None:
    unique = sorted(allowed_commands)
    for pid in unique:
        if not _process_is_present(pid):
            continue
        command = _command_for_pid(pid)
        if command is None:
            continue
        if not all(token in f" {command} " for token in allowed_commands[pid]):
            raise LaunchGateError(
                "Managed process identity changed before reconciliation"
            )
        if _process_cwd(pid) != expected_cwd:
            raise LaunchGateError(
                "Managed launch process has an unexpected directory"
            )
        if not _process_is_present(pid):
            continue
        command = _command_for_pid(pid)
        if command is None:
            continue
        if not all(token in f" {command} " for token in allowed_commands[pid]):
            raise LaunchGateError(
                "Managed process identity changed before signal"
            )
        if _process_cwd(pid) != expected_cwd:
            raise LaunchGateError(
                "Managed process directory changed before signal"
            )
        os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + 10.0
    for pid in unique:
        while _process_is_present(pid) and time.monotonic() < deadline:
            time.sleep(0.05)
        if _process_is_present(pid):
            raise LaunchGateError(
                "Managed launch process did not stop during reconciliation"
            )


def _complete_launch(
    *,
    intent: Path,
    gate: Path,
    pid_file: Path,
    service: str,
    expected_cwd: Path,
    signature: str,
) -> None:
    _, parent_descriptor = _open_private_parent((intent, gate, pid_file))
    try:
        evidence = _read_launch_evidence(
            intent=intent,
            gate=gate,
            service=service,
            expected_cwd=expected_cwd,
            signature=signature,
            parent_descriptor=parent_descriptor,
            gate_required=True,
        )
        pid_record = _read_decimal_pid(pid_file, parent_descriptor)
        pid = int(pid_record.values["pid"])
        command = dict(_process_rows()).get(pid, "")
        if (
            evidence.gate is None
            or evidence.gate.values["pid"] != str(pid)
            or not _process_is_present(pid)
            or signature not in command
            or _is_gate_wrapper(
                command,
                intent=intent,
                gate=gate,
                service=service,
                nonce=evidence.nonce,
            )
            or _process_cwd(pid) != expected_cwd
        ):
            raise LaunchGateError(
                "Managed launch completion does not match the live PID"
            )
        # Keep the PID-bound intent and gate for the service lifetime. They are
        # the durable proof that this process was allowed to execute and are
        # removed only after reconciliation has stopped the exact service.
    finally:
        os.close(parent_descriptor)


def _reconcile_launch(
    *,
    intent: Path,
    gate: Path,
    pid_file: Path,
    service: str,
    expected_cwd: Path,
    signature: str,
) -> None:
    _, parent_descriptor = _open_private_parent((intent, gate, pid_file))
    try:
        intent_exists = _record_exists(intent.name, parent_descriptor)
        gate_exists = _record_exists(gate.name, parent_descriptor)
        pid_exists = _record_exists(pid_file.name, parent_descriptor)
        if gate_exists and not intent_exists:
            raise LaunchGateError(
                "Managed launch gate exists without its durable intent"
            )

        evidence: LaunchEvidence | None = None
        if intent_exists:
            evidence = _read_launch_evidence(
                intent=intent,
                gate=gate,
                service=service,
                expected_cwd=expected_cwd,
                signature=signature,
                parent_descriptor=parent_descriptor,
                gate_required=False,
            )
        pid_record = (
            _read_decimal_pid(pid_file, parent_descriptor)
            if pid_exists
            else None
        )
        rows = _process_rows()
        by_pid = dict(rows)
        all_wrapper_pids = [
            pid
            for pid, command in rows
            if _is_gate_wrapper(
                command,
                intent=intent,
                gate=gate,
                service=service,
                nonce=None,
            )
        ]
        wrapper_pids = [
            pid
            for pid, command in rows
            if _is_gate_wrapper(
                command,
                intent=intent,
                gate=gate,
                service=service,
                nonce=evidence.nonce if evidence else None,
            )
        ]
        if set(all_wrapper_pids) != set(wrapper_pids):
            raise LaunchGateError(
                "A managed launch wrapper has an unexpected nonce"
            )

        # Without durable launch evidence, leave an ordinary service PID to the
        # established identity-aware stop path.  Only a torn gate wrapper is
        # reconciled here.
        if evidence is None and not wrapper_pids:
            # This is also the retry path after the last visible unlink but
            # before its parent-directory barrier completed.
            full_sync_fd(parent_descriptor)
            return

        allowed_commands: dict[int, tuple[str, ...]] = {
            pid: (
                "gated_service_exec.py",
                " hold ",
                str(intent),
                str(gate),
                f"--service {service}",
                (
                    f"--nonce {evidence.nonce}"
                    if evidence is not None
                    else "--nonce "
                ),
            )
            for pid in wrapper_pids
        }
        if pid_record is not None:
            pid = int(pid_record.values["pid"])
            command = by_pid.get(pid)
            if command is not None:
                if _is_gate_wrapper(
                    command,
                    intent=intent,
                    gate=gate,
                    service=service,
                    nonce=evidence.nonce if evidence else None,
                ):
                    allowed_commands[pid] = (
                        "gated_service_exec.py",
                        " hold ",
                        str(intent),
                        str(gate),
                        f"--service {service}",
                        (
                            f"--nonce {evidence.nonce}"
                            if evidence is not None
                            else "--nonce "
                        ),
                    )
                elif evidence is not None and signature in command:
                    if evidence.gate is None:
                        raise LaunchGateError(
                            "Service executed before its durable launch gate"
                        )
                    allowed_commands[pid] = (signature,)
                else:
                    raise LaunchGateError(
                        "Managed PID belongs to an unexpected process"
                    )

        if evidence is not None and evidence.gate is not None:
            gate_pid = int(evidence.gate.values["pid"])
            if pid_record is not None and (
                evidence.gate.values["pid"] != pid_record.values["pid"]
            ):
                raise LaunchGateError(
                    "Managed launch gate is not bound to the durable PID"
                )
            if pid_record is None:
                command = by_pid.get(gate_pid)
                if command is not None:
                    if _is_gate_wrapper(
                        command,
                        intent=intent,
                        gate=gate,
                        service=service,
                        nonce=evidence.nonce,
                    ):
                        allowed_commands[gate_pid] = (
                            "gated_service_exec.py",
                            " hold ",
                            str(intent),
                            str(gate),
                            f"--service {service}",
                            f"--nonce {evidence.nonce}",
                        )
                    elif signature in command:
                        allowed_commands[gate_pid] = (signature,)
                    else:
                        raise LaunchGateError(
                            "Gate-bound PID belongs to an unexpected process"
                        )

        _terminate_exact_processes(
            allowed_commands,
            expected_cwd=expected_cwd,
        )
        records: list[tuple[Path, PrivateRecord]] = []
        if pid_record is not None:
            records.append((pid_file, pid_record))
        if evidence is not None and evidence.gate is not None:
            records.append((gate, evidence.gate))
        if evidence is not None:
            records.append((intent, evidence.intent))
        if records:
            _remove_records(records, parent_descriptor=parent_descriptor)
    finally:
        os.close(parent_descriptor)


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--intent", type=Path, required=True)
    parser.add_argument("--gate", type=Path, required=True)
    parser.add_argument("--service", choices=sorted(_SERVICES), required=True)
    parser.add_argument("--expected-cwd", type=Path, required=True)
    parser.add_argument("--signature", required=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="operation", required=True)

    hold = commands.add_parser("hold")
    _add_common_arguments(hold)
    hold.add_argument("--pid-file", type=Path, required=True)
    hold.add_argument("--nonce", required=True)
    hold.add_argument("--timeout-seconds", type=float, default=15.0)
    hold.add_argument("command", nargs=argparse.REMAINDER)

    complete = commands.add_parser("complete")
    _add_common_arguments(complete)
    complete.add_argument("--pid-file", type=Path, required=True)

    reconcile = commands.add_parser("reconcile")
    _add_common_arguments(reconcile)
    reconcile.add_argument("--pid-file", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    expected_cwd = args.expected_cwd.resolve(strict=True)
    if (
        not expected_cwd.is_dir()
        or not args.signature
        or args.intent.name != f"{args.service}.launching"
        or args.gate.name != f"{args.service}.gate"
        or args.pid_file.name != f"{args.service}.pid"
    ):
        raise LaunchGateError("Managed launch identity is invalid")
    if args.operation == "hold":
        command = list(args.command)
        if command and command[0] == "--":
            command.pop(0)
        _validate_nonce(args.nonce)
        if args.timeout_seconds <= 0 or not command:
            raise LaunchGateError("Managed launch hold arguments are invalid")
        _wait_for_gate(
            intent=args.intent,
            gate=args.gate,
            pid_file=args.pid_file,
            service=args.service,
            nonce=args.nonce,
            expected_cwd=expected_cwd,
            signature=args.signature,
            timeout_seconds=args.timeout_seconds,
        )
        os.chdir(expected_cwd)
        os.execvp(command[0], command)
        return 1
    if args.operation == "complete":
        _complete_launch(
            intent=args.intent,
            gate=args.gate,
            pid_file=args.pid_file,
            service=args.service,
            expected_cwd=expected_cwd,
            signature=args.signature,
        )
        return 0
    _reconcile_launch(
        intent=args.intent,
        gate=args.gate,
        pid_file=args.pid_file,
        service=args.service,
        expected_cwd=expected_cwd,
        signature=args.signature,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
