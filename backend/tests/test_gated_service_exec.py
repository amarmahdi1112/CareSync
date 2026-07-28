"""Crash-edge tests for durable managed-service launch handoff."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from scripts import gated_service_exec
from scripts.gated_service_exec import LaunchGateError

SERVICE = "frontend"
SIGNATURE = "/bin/sleep 60"
NONCE = "a" * 64


def _can_inspect_processes() -> bool:
    if sys.platform != "darwin":
        return False
    try:
        result = subprocess.run(
            ["/bin/ps", "-p", str(os.getpid()), "-o", "pid="],
            check=False,
            capture_output=True,
            text=True,
        )
    except PermissionError:
        return False
    return result.returncode == 0 and result.stdout.strip() == str(os.getpid())


CAN_INSPECT_PROCESSES = _can_inspect_processes()


def _private_directory(tmp_path: Path) -> Path:
    directory = tmp_path / "pids"
    directory.mkdir(mode=0o700)
    directory.chmod(0o700)
    return directory


def _paths(directory: Path) -> tuple[Path, Path, Path]:
    return (
        directory / f"{SERVICE}.launching",
        directory / f"{SERVICE}.gate",
        directory / f"{SERVICE}.pid",
    )


def _write_private(path: Path, payload: str) -> None:
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )
    try:
        os.write(descriptor, payload.encode("utf-8"))
    finally:
        os.close(descriptor)
    path.chmod(0o600)


def _write_intent(path: Path, cwd: Path) -> None:
    expected_cwd = cwd.resolve()
    _write_private(
        path,
        "\n".join(
            (
                "status=managed_launch_pending",
                f"service={SERVICE}",
                f"nonce={NONCE}",
                f"parent_pid={os.getpid()}",
                f"expected_cwd={expected_cwd}",
                f"signature={SIGNATURE}",
                "",
            )
        ),
    )


def _write_pid(path: Path, pid: int) -> None:
    _write_private(path, f"{pid}\n")


def _write_gate(path: Path, pid: int) -> None:
    _write_private(
        path,
        "\n".join(
            (
                "status=managed_launch_released",
                f"service={SERVICE}",
                f"nonce={NONCE}",
                f"pid={pid}",
                "",
            )
        ),
    )


def _record(path: Path, values: dict[str, str]) -> gated_service_exec.PrivateRecord:
    details = path.stat()
    return gated_service_exec.PrivateRecord(
        values=values,
        device=details.st_dev,
        inode=details.st_ino,
    )


def _hold_arguments(
    intent: Path,
    gate: Path,
    pid_file: Path,
    cwd: Path,
    *,
    timeout: float,
) -> list[str]:
    return [
        "hold",
        "--intent",
        str(intent),
        "--gate",
        str(gate),
        "--pid-file",
        str(pid_file),
        "--service",
        SERVICE,
        "--nonce",
        NONCE,
        "--expected-cwd",
        str(cwd),
        "--signature",
        SIGNATURE,
        "--timeout-seconds",
        str(timeout),
        "--",
        "/bin/sleep",
        "60",
    ]


def _reconcile(
    intent: Path,
    gate: Path,
    pid_file: Path,
    cwd: Path,
) -> None:
    gated_service_exec.main(
        [
            "reconcile",
            "--intent",
            str(intent),
            "--gate",
            str(gate),
            "--pid-file",
            str(pid_file),
            "--service",
            SERVICE,
            "--expected-cwd",
            str(cwd),
            "--signature",
            SIGNATURE,
        ]
    )


def _wait_for_command(
    pid: int,
    token: str,
    *,
    absent_token: str | None = None,
) -> None:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        result = subprocess.run(
            ["/bin/ps", "-p", str(pid), "-ww", "-o", "command="],
            check=False,
            capture_output=True,
            text=True,
        )
        if token in result.stdout and (
            absent_token is None or absent_token not in result.stdout
        ):
            return
        time.sleep(0.05)
    raise AssertionError(
        f"PID {pid} never exposed command token {token!r} "
        f"without {absent_token!r}"
    )


def test_child_times_out_without_durable_pid_and_gate(tmp_path: Path) -> None:
    directory = _private_directory(tmp_path)
    intent, gate, pid_file = _paths(directory)
    _write_intent(intent, tmp_path)

    with pytest.raises(LaunchGateError, match="timed out"):
        gated_service_exec.main(
            _hold_arguments(
                intent,
                gate,
                pid_file,
                tmp_path,
                timeout=0.01,
            )
        )


def test_child_rejects_gate_without_durable_pid(tmp_path: Path) -> None:
    directory = _private_directory(tmp_path)
    intent, gate, pid_file = _paths(directory)
    _write_intent(intent, tmp_path)
    _write_gate(gate, os.getpid())

    with pytest.raises(LaunchGateError, match="PID record"):
        gated_service_exec.main(
            _hold_arguments(
                intent,
                gate,
                pid_file,
                tmp_path,
                timeout=0.1,
            )
        )


def test_child_executes_only_after_pid_bound_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    directory = _private_directory(tmp_path)
    intent, gate, pid_file = _paths(directory)
    _write_intent(intent, tmp_path)
    _write_pid(pid_file, os.getpid())
    _write_gate(gate, os.getpid())
    executed: list[tuple[str, list[str]]] = []

    def capture_exec(executable: str, command: list[str]) -> None:
        executed.append((executable, command))
        raise RuntimeError("exec captured")

    monkeypatch.setattr(gated_service_exec.os, "execvp", capture_exec)
    monkeypatch.setattr(gated_service_exec.os, "chdir", lambda _path: None)
    with pytest.raises(RuntimeError, match="exec captured"):
        gated_service_exec.main(
            _hold_arguments(
                intent,
                gate,
                pid_file,
                tmp_path,
                timeout=0.1,
            )
        )

    assert executed == [("/bin/sleep", ["/bin/sleep", "60"])]


def test_reconcile_intent_before_fork(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    directory = _private_directory(tmp_path)
    intent, gate, pid_file = _paths(directory)
    _write_intent(intent, tmp_path)
    monkeypatch.setattr(gated_service_exec, "_process_rows", lambda: [])

    _reconcile(intent, gate, pid_file, tmp_path)

    assert not intent.exists()
    assert not gate.exists()
    assert not pid_file.exists()


@pytest.mark.parametrize("failed_barrier", (1, 2, 3))
def test_reconcile_recovers_each_ordered_cleanup_crash_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failed_barrier: int,
) -> None:
    directory = _private_directory(tmp_path)
    intent, gate, pid_file = _paths(directory)
    _write_intent(intent, tmp_path)
    _write_gate(gate, 999_999)
    _write_pid(pid_file, 999_999)
    intent_record = _record(intent, {})
    gate_record = _record(gate, {})
    pid_record = _record(pid_file, {})
    original_full_sync = gated_service_exec.full_sync_fd
    barriers = 0

    def fail_at_selected_barrier(descriptor: int) -> None:
        nonlocal barriers
        barriers += 1
        if barriers == failed_barrier:
            raise OSError("simulated power-loss barrier")
        original_full_sync(descriptor)

    monkeypatch.setattr(
        gated_service_exec,
        "full_sync_fd",
        fail_at_selected_barrier,
    )
    _, parent_descriptor = gated_service_exec._open_private_parent(
        (intent, gate, pid_file)
    )
    try:
        with pytest.raises(OSError, match="simulated power-loss"):
            gated_service_exec._remove_records(
                (
                    (pid_file, pid_record),
                    (gate, gate_record),
                    (intent, intent_record),
                ),
                parent_descriptor=parent_descriptor,
            )
    finally:
        os.close(parent_descriptor)

    monkeypatch.setattr(
        gated_service_exec,
        "full_sync_fd",
        original_full_sync,
    )
    monkeypatch.setattr(gated_service_exec, "_process_rows", lambda: [])
    _reconcile(intent, gate, pid_file, tmp_path)

    assert not pid_file.exists()
    assert not gate.exists()
    assert not intent.exists()


@pytest.mark.skipif(
    not CAN_INSPECT_PROCESSES,
    reason="Darwin process/cwd inspection is unavailable",
)
def test_reconcile_fork_before_pid_publication(tmp_path: Path) -> None:
    directory = _private_directory(tmp_path)
    intent, gate, pid_file = _paths(directory)
    _write_intent(intent, tmp_path)
    process = subprocess.Popen(
        [
            sys.executable,
            str(Path(gated_service_exec.__file__).resolve()),
            *_hold_arguments(
                intent,
                gate,
                pid_file,
                tmp_path,
                timeout=60,
            ),
        ],
        cwd=tmp_path,
    )
    try:
        _wait_for_command(process.pid, "gated_service_exec.py")
        _reconcile(intent, gate, pid_file, tmp_path)
        process.wait(timeout=5)
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)

    assert not intent.exists()
    assert not pid_file.exists()


@pytest.mark.skipif(
    not CAN_INSPECT_PROCESSES,
    reason="Darwin process/cwd inspection is unavailable",
)
def test_reconcile_pid_before_gate_publication(tmp_path: Path) -> None:
    directory = _private_directory(tmp_path)
    intent, gate, pid_file = _paths(directory)
    _write_intent(intent, tmp_path)
    process = subprocess.Popen(
        [
            sys.executable,
            str(Path(gated_service_exec.__file__).resolve()),
            *_hold_arguments(
                intent,
                gate,
                pid_file,
                tmp_path,
                timeout=60,
            ),
        ],
        cwd=tmp_path,
    )
    try:
        _write_pid(pid_file, process.pid)
        _wait_for_command(process.pid, "gated_service_exec.py")
        _reconcile(intent, gate, pid_file, tmp_path)
        process.wait(timeout=5)
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)

    assert not intent.exists()
    assert not pid_file.exists()


@pytest.mark.skipif(
    not CAN_INSPECT_PROCESSES,
    reason="Darwin process/cwd inspection is unavailable",
)
def test_lifetime_evidence_survives_exec_then_reconciles(
    tmp_path: Path,
) -> None:
    directory = _private_directory(tmp_path)
    intent, gate, pid_file = _paths(directory)
    _write_intent(intent, tmp_path)
    process = subprocess.Popen(
        [
            sys.executable,
            str(Path(gated_service_exec.__file__).resolve()),
            *_hold_arguments(
                intent,
                gate,
                pid_file,
                tmp_path,
                timeout=60,
            ),
        ],
        cwd=tmp_path,
    )
    try:
        _write_pid(pid_file, process.pid)
        _write_gate(gate, process.pid)
        _wait_for_command(
            process.pid,
            "/bin/sleep 60",
            absent_token="gated_service_exec.py",
        )
        result = gated_service_exec.main(
            [
                "complete",
                "--intent",
                str(intent),
                "--gate",
                str(gate),
                "--pid-file",
                str(pid_file),
                "--service",
                SERVICE,
                "--expected-cwd",
                str(tmp_path),
                "--signature",
                SIGNATURE,
            ]
        )
        assert result == 0
        assert intent.exists()
        assert gate.exists()
        assert pid_file.exists()

        _reconcile(intent, gate, pid_file, tmp_path)
        process.wait(timeout=5)
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)

    assert not intent.exists()
    assert not gate.exists()
    assert not pid_file.exists()


def test_reconcile_rechecks_command_before_signal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands = iter(("/bin/sleep 60", "/bin/echo identity-changed"))
    signaled: list[tuple[int, signal.Signals]] = []
    monkeypatch.setattr(
        gated_service_exec,
        "_process_is_present",
        lambda _pid: True,
    )
    monkeypatch.setattr(
        gated_service_exec,
        "_process_cwd",
        lambda _pid: tmp_path,
    )
    monkeypatch.setattr(
        gated_service_exec,
        "_command_for_pid",
        lambda _pid: next(commands),
    )
    monkeypatch.setattr(
        gated_service_exec.os,
        "kill",
        lambda pid, sent_signal: signaled.append((pid, sent_signal)),
    )

    with pytest.raises(LaunchGateError, match="identity changed"):
        gated_service_exec._terminate_exact_processes(
            {43210: (SIGNATURE,)},
            expected_cwd=tmp_path,
        )

    assert signaled == []


def test_reconcile_rechecks_cwd_immediately_before_signal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    directories = iter((tmp_path, tmp_path / "reused"))
    signaled: list[tuple[int, signal.Signals]] = []
    monkeypatch.setattr(
        gated_service_exec,
        "_process_is_present",
        lambda _pid: True,
    )
    monkeypatch.setattr(
        gated_service_exec,
        "_process_cwd",
        lambda _pid: next(directories),
    )
    monkeypatch.setattr(
        gated_service_exec,
        "_command_for_pid",
        lambda _pid: "/bin/sleep 60",
    )
    monkeypatch.setattr(
        gated_service_exec.os,
        "kill",
        lambda pid, sent_signal: signaled.append((pid, sent_signal)),
    )

    with pytest.raises(LaunchGateError, match="directory changed"):
        gated_service_exec._terminate_exact_processes(
            {43211: (SIGNATURE,)},
            expected_cwd=tmp_path,
        )

    assert signaled == []
