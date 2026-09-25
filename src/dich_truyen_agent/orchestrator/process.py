from __future__ import annotations

import ctypes
from collections.abc import Callable
from datetime import UTC, datetime
import os
from pathlib import Path
import re
import signal
import subprocess
import threading
import time
from typing import Any

from pydantic import BaseModel, Field


class ProcessResult(BaseModel):
    exit_code: int | None = None
    timed_out: bool = False
    cancelled: bool = False
    started_at: datetime
    finished_at: datetime
    stdout_path: Path
    stderr_path: Path
    failure_detail: str | None = None
    argv: list[str] = Field(default_factory=list)


# Secret scrubbing patterns
_SECRET_PATTERNS = [
    re.compile(r"(Bearer\s+)[A-Za-z0-9_\-\.]{10,}", re.IGNORECASE),
    re.compile(r"(sk-[A-Za-z0-9_\-]{10,})", re.IGNORECASE),
    re.compile(r"(ghp_[A-Za-z0-9]{20,})", re.IGNORECASE),
    re.compile(r"(password|token|secret|api_key|apikey)=([^&\s]+)", re.IGNORECASE),
]


def scrub_sensitive_text(text: str) -> str:
    """Mask common API keys, tokens, and credentials in process output."""
    scrubbed = text
    for pattern in _SECRET_PATTERNS:
        scrubbed = pattern.sub(r"\1[REDACTED]", scrubbed)
    return scrubbed


# Windows Job Object Structures and API
if os.name == "nt":

    class _IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    class _JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", ctypes.c_uint32),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", ctypes.c_uint32),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", ctypes.c_uint32),
            ("SchedulingClass", ctypes.c_uint32),
        ]

    class _JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", _IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryLimit", ctypes.c_size_t),
            ("PeakJobMemoryLimit", ctypes.c_size_t),
        ]

    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
    JobObjectExtendedLimitInformation = 9


class WindowsJobObject:
    """Encapsulates a Windows Job Object configured to kill child trees on close."""

    def __init__(self) -> None:
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.handle = self._kernel32.CreateJobObjectW(None, None)
        if not self.handle:
            raise OSError(f"CreateJobObjectW failed with error {ctypes.get_last_error()}")

        info = _JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        res = self._kernel32.SetInformationJobObject(
            self.handle,
            JobObjectExtendedLimitInformation,
            ctypes.byref(info),
            ctypes.sizeof(info),
        )
        if not res:
            err = ctypes.get_last_error()
            self.close()
            raise OSError(f"SetInformationJobObject failed with error {err}")

    def assign_process(self, proc_handle: int) -> bool:
        if self.handle:
            res = self._kernel32.AssignProcessToJobObject(self.handle, proc_handle)
            return bool(res)
        return False

    def terminate(self, exit_code: int = 1) -> bool:
        if self.handle:
            res = self._kernel32.TerminateJobObject(self.handle, exit_code)
            return bool(res)
        return False

    def close(self) -> None:
        if self.handle:
            self._kernel32.CloseHandle(self.handle)
            self.handle = None


def _drain_stream(
    stream: Any,
    file_path: Path,
    tail_buffer: bytearray,
    tail_lock: threading.Lock,
    on_event: Callable[[dict[str, Any]], None] | None,
    stream_name: str,
    max_tail_bytes: int = 4096,
) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    line_buf = bytearray()
    with file_path.open("wb") as f:
        while True:
            chunk = stream.read(4096)
            if not chunk:
                break
            f.write(chunk)
            f.flush()
            with tail_lock:
                tail_buffer.extend(chunk)
                if len(tail_buffer) > max_tail_bytes:
                    del tail_buffer[: len(tail_buffer) - max_tail_bytes]

            if on_event:
                line_buf.extend(chunk)
                while b"\n" in line_buf:
                    line, _, line_buf = line_buf.partition(b"\n")
                    text_line = line.decode("utf-8", errors="replace").rstrip("\r")
                    scrubbed = scrub_sensitive_text(text_line)
                    try:
                        on_event({"event": "stream", "stream": stream_name, "text": scrubbed})
                    except Exception:
                        pass

        if on_event and line_buf:
            text_line = line_buf.decode("utf-8", errors="replace").rstrip("\r")
            scrubbed = scrub_sensitive_text(text_line)
            try:
                on_event({"event": "stream", "stream": stream_name, "text": scrubbed})
            except Exception:
                pass


def run_process(
    argv: list[str],
    *,
    cwd: Path | str | None = None,
    env: dict[str, str] | None = None,
    timeout_seconds: float | None = None,
    stdout_path: Path | str,
    stderr_path: Path | str,
    on_event: Callable[[dict[str, Any]], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> ProcessResult:
    """Supervise a subprocess tree with concurrent stream draining, Job Object / process group reaping,

    and wall-clock timeout.
    """
    stdout_file = Path(stdout_path).resolve()
    stderr_file = Path(stderr_path).resolve()
    working_dir = Path(cwd).resolve() if cwd else None

    # Environment preparation: inherit parent env and update if provided
    proc_env = os.environ.copy()
    if env:
        proc_env.update(env)

    started_at = datetime.now(UTC)

    # Platform setup
    job_object = WindowsJobObject() if os.name == "nt" else None
    popen_kwargs: dict[str, Any] = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "cwd": working_dir,
        "env": proc_env,
        "shell": False,
    }

    if os.name != "nt":
        popen_kwargs["start_new_session"] = True

    try:
        proc = subprocess.Popen(argv, **popen_kwargs)
    except Exception as exc:
        if job_object:
            job_object.close()
        finished_at = datetime.now(UTC)
        stdout_file.parent.mkdir(parents=True, exist_ok=True)
        stderr_file.parent.mkdir(parents=True, exist_ok=True)
        stderr_file.write_text(f"failed to start process: {exc}\n", encoding="utf-8")
        return ProcessResult(
            exit_code=1,
            timed_out=False,
            cancelled=False,
            started_at=started_at,
            finished_at=finished_at,
            stdout_path=stdout_file,
            stderr_path=stderr_file,
            failure_detail=f"failed to start process: {exc}",
            argv=argv,
        )

    # Bind to Windows Job Object
    if job_object:
        assigned = job_object.assign_process(int(proc._handle))
        if not assigned and proc.poll() is None:
            err = ctypes.get_last_error()
            job_object.terminate(1)
            job_object.close()
            proc.kill()
            raise OSError(f"AssignProcessToJobObject failed with error {err}")

    if on_event:
        try:
            on_event({"event": "started", "pid": proc.pid, "argv": argv, "timestamp": started_at.isoformat()})
        except Exception:
            pass

    tail_lock = threading.Lock()
    stdout_tail = bytearray()
    stderr_tail = bytearray()

    t_stdout = threading.Thread(
        target=_drain_stream,
        args=(proc.stdout, stdout_file, stdout_tail, tail_lock, on_event, "stdout"),
        daemon=True,
    )
    t_stderr = threading.Thread(
        target=_drain_stream,
        args=(proc.stderr, stderr_file, stderr_tail, tail_lock, on_event, "stderr"),
        daemon=True,
    )
    t_stdout.start()
    t_stderr.start()

    start_monotonic = time.monotonic()
    timed_out = False
    cancelled = False

    while True:
        if cancel_event and cancel_event.is_set():
            cancelled = True
            break

        ret = proc.poll()
        if ret is not None:
            break

        if timeout_seconds is not None:
            elapsed = time.monotonic() - start_monotonic
            if elapsed >= timeout_seconds:
                timed_out = True
                break

        time.sleep(0.02)

    # Shutdown on timeout or cancellation
    if timed_out or cancelled:
        if job_object:
            job_object.terminate(1)
        elif os.name != "nt":
            try:
                pgid = os.getpgid(proc.pid)
                os.killpg(pgid, signal.SIGTERM)
                time.sleep(0.05)
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        else:
            proc.kill()

        try:
            proc.wait(timeout=3.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=1.0)

    # Wait for natural exit if still running
    proc.wait()

    # Wait for pipe readers to finish draining
    t_stdout.join(timeout=3.0)
    t_stderr.join(timeout=3.0)

    # Close Job Object on Windows
    if job_object:
        job_object.close()

    finished_at = datetime.now(UTC)
    exit_code = proc.poll()

    with tail_lock:
        err_text = bytes(stderr_tail).decode("utf-8", errors="replace").strip()
        out_text = bytes(stdout_tail).decode("utf-8", errors="replace").strip()

    failure_detail: str | None = None
    if timed_out:
        failure_detail = f"Process timed out after {timeout_seconds} seconds"
        if err_text:
            failure_detail += f"\nstderr:\n{scrub_sensitive_text(err_text[-2000:])}"
    elif cancelled:
        failure_detail = "Process was cancelled"
    elif exit_code != 0:
        if err_text:
            failure_detail = scrub_sensitive_text(err_text[-2000:])
        elif out_text:
            failure_detail = scrub_sensitive_text(out_text[-2000:])
        else:
            failure_detail = f"Process exited with code {exit_code}"

    if on_event:
        try:
            on_event({
                "event": "finished",
                "exit_code": exit_code,
                "timed_out": timed_out,
                "cancelled": cancelled,
                "timestamp": finished_at.isoformat(),
            })
        except Exception:
            pass

    return ProcessResult(
        exit_code=exit_code,
        timed_out=timed_out,
        cancelled=cancelled,
        started_at=started_at,
        finished_at=finished_at,
        stdout_path=stdout_file,
        stderr_path=stderr_file,
        failure_detail=failure_detail,
        argv=argv,
    )
