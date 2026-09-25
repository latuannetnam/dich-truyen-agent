from __future__ import annotations

import ctypes
from dataclasses import dataclass
import os
from pathlib import Path
import sys
import threading
import time

import pytest

from dich_truyen_agent.orchestrator.process import run_process


def is_pid_alive(pid: int) -> bool:
    """Check if process with given PID is currently active."""
    if os.name == "nt":
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        h_proc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if h_proc == 0:
            return False
        exit_code = ctypes.c_ulong()
        kernel32.GetExitCodeProcess(h_proc, ctypes.byref(exit_code))
        kernel32.CloseHandle(h_proc)
        STILL_ACTIVE = 259
        return exit_code.value == STILL_ACTIVE
    else:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


@dataclass
class ProcessFixture:
    tmp_path: Path
    paths: dict[str, Path]
    quiet_argv: list[str]
    nonzero_argv: list[str]
    pipes_argv: list[str]
    grandchild_argv: list[str]
    grandchild_pid_file: Path


@pytest.fixture
def process_fixture(tmp_path: Path) -> ProcessFixture:
    stdout_path = tmp_path / "stdout.log"
    stderr_path = tmp_path / "stderr.log"
    pid_file = tmp_path / "grandchild.pid"

    # 1. Quiet script: sleeps for 0.8s without producing output
    quiet_code = "import time; time.sleep(0.8)"
    quiet_argv = [sys.executable, "-c", quiet_code]

    # 2. Nonzero script: writes error to stderr and exits with 42
    nonzero_code = (
        "import sys\n"
        "sys.stderr.write('fatal: something failed spectacularly\\n')\n"
        "sys.exit(42)\n"
    )
    nonzero_argv = [sys.executable, "-c", nonzero_code]

    # 3. Pipes script: writes large volume (> 100KB) to both stdout and stderr
    pipes_code = (
        "import sys\n"
        "chunk = 'A' * 2048 + '\\n'\n"
        "err_chunk = 'B' * 2048 + '\\n'\n"
        "for _ in range(60):\n"
        "    sys.stdout.write(chunk)\n"
        "    sys.stderr.write(err_chunk)\n"
        "sys.stdout.flush()\n"
        "sys.stderr.flush()\n"
    )
    pipes_argv = [sys.executable, "-c", pipes_code]

    # 4. Grandchild script: spawns grandchild that sleeps for 60s, records PID
    grandchild_code = (
        f"import subprocess, sys, time, pathlib\n"
        f"p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        f"pathlib.Path({str(pid_file)!r}).write_text(str(p.pid), encoding='utf-8')\n"
        f"time.sleep(60)\n"
    )
    grandchild_argv = [sys.executable, "-c", grandchild_code]

    return ProcessFixture(
        tmp_path=tmp_path,
        paths={"stdout_path": stdout_path, "stderr_path": stderr_path},
        quiet_argv=quiet_argv,
        nonzero_argv=nonzero_argv,
        pipes_argv=pipes_argv,
        grandchild_argv=grandchild_argv,
        grandchild_pid_file=pid_file,
    )


def test_quiet_child_uses_wall_clock_not_idle_timeout(process_fixture: ProcessFixture) -> None:
    result = run_process(process_fixture.quiet_argv, timeout_seconds=2, **process_fixture.paths)
    assert result.exit_code == 0
    assert result.timed_out is False
    assert result.cancelled is False


def test_nonzero_child_reports_code_and_failure_detail(process_fixture: ProcessFixture) -> None:
    result = run_process(process_fixture.nonzero_argv, **process_fixture.paths)
    assert result.exit_code == 42
    assert result.timed_out is False
    assert result.cancelled is False
    assert process_fixture.paths["stderr_path"].is_file()
    assert "fatal: something failed spectacularly" in process_fixture.paths["stderr_path"].read_text(encoding="utf-8")
    assert result.failure_detail is not None
    assert "something failed spectacularly" in result.failure_detail


def test_fill_both_pipes_concurrently_without_deadlock(process_fixture: ProcessFixture) -> None:
    result = run_process(process_fixture.pipes_argv, timeout_seconds=10, **process_fixture.paths)
    assert result.exit_code == 0
    assert result.timed_out is False

    stdout_bytes = process_fixture.paths["stdout_path"].read_bytes()
    stderr_bytes = process_fixture.paths["stderr_path"].read_bytes()

    assert len(stdout_bytes) >= 100000
    assert len(stderr_bytes) >= 100000


def test_timeout_kills_full_process_tree_including_grandchild(process_fixture: ProcessFixture) -> None:
    # Run grandchild script with short timeout
    result = run_process(
        process_fixture.grandchild_argv,
        timeout_seconds=1.5,
        **process_fixture.paths,
    )

    assert result.timed_out is True
    assert result.failure_detail is not None
    assert "timed out after 1.5 seconds" in result.failure_detail

    # Verify grandchild was spawned and then killed
    assert process_fixture.grandchild_pid_file.is_file()
    grandchild_pid = int(process_fixture.grandchild_pid_file.read_text(encoding="utf-8").strip())

    time.sleep(0.5)
    assert is_pid_alive(grandchild_pid) is False


def test_cancellation_kills_full_process_tree(process_fixture: ProcessFixture) -> None:
    cancel_event = threading.Event()

    def cancel_after_started() -> None:
        # Wait for grandchild PID file to be written
        for _ in range(50):
            if process_fixture.grandchild_pid_file.is_file():
                break
            time.sleep(0.05)
        cancel_event.set()

    thread = threading.Thread(target=cancel_after_started)
    thread.start()

    result = run_process(
        process_fixture.grandchild_argv,
        timeout_seconds=15,
        cancel_event=cancel_event,
        **process_fixture.paths,
    )
    thread.join()

    assert result.cancelled is True
    assert process_fixture.grandchild_pid_file.is_file()
    grandchild_pid = int(process_fixture.grandchild_pid_file.read_text(encoding="utf-8").strip())

    time.sleep(0.5)
    assert is_pid_alive(grandchild_pid) is False


def test_on_event_scrubs_secrets_and_captures_lifecycle(tmp_path: Path) -> None:
    events: list[dict] = []

    def on_event(ev: dict) -> None:
        events.append(ev)

    stdout_path = tmp_path / "stdout.log"
    stderr_path = tmp_path / "stderr.log"

    script = (
        "import sys\n"
        "print('Authorization: Bearer sk-ant-secret12345678901234567890', flush=True)\n"
        "print('Clean line without secret', flush=True)\n"
    )
    argv = [sys.executable, "-c", script]

    result = run_process(
        argv,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        on_event=on_event,
    )

    assert result.exit_code == 0
    event_types = [e.get("event") for e in events]
    assert "started" in event_types
    assert "stream" in event_types
    assert "finished" in event_types

    # Ensure secret was scrubbed in stream events
    stream_texts = [e.get("text", "") for e in events if e.get("event") == "stream"]
    all_text = " ".join(stream_texts)
    assert "sk-ant-secret" not in all_text
    assert "[REDACTED]" in all_text
