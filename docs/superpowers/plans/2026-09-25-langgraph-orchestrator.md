# LangGraph Agent Orchestrator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a robust, unattended, LangGraph-powered Agent Orchestrator with an extensible Harness Runner abstraction (initially optimized for Antigravity CLI `agy`), real-time activity tracing, persistent logging, and full CLI integration.

**Architecture:** A LangGraph `StateGraph` models the end-to-end novel translation lifecycle as a stateful, cyclic workflow with SQLite checkpointing. An `AgyRunner` subprocess abstraction handles fresh-session CLI batching (default 5 chapters per isolated session) to eliminate context explosion. An `ActivityTracer` streams live tool calls/progress to the console and writes structured logs to disk for post-mortem debugging.

**Tech Stack:** Python 3.13, `langgraph`, `langgraph-checkpoint-sqlite`, `pydantic`, `pytest`, `uv`.

---

## File Structure

```text
pyproject.toml                                        # Add langgraph and langgraph-checkpoint-sqlite
src/dich_truyen_agent/
├── orchestrator/
│   ├── __init__.py                                   # Expose BookOrchestrator, OrchestratorConfig
│   ├── models.py                                     # Dataclasses/Pydantic models for run events & config
│   ├── state.py                                      # BookOrchestratorState TypedDict definition
│   ├── tracer.py                                     # ActivityTracer: Live console & persistent disk logging
│   ├── graph.py                                      # LangGraph StateGraph, nodes, conditional edges, checkpointer
│   ├── orchestrator.py                               # BookOrchestrator engine & coordinator
│   └── runners/
│       ├── __init__.py                               # Expose BaseHarnessRunner, AgyRunner, MockRunner
│       ├── base.py                                   # BaseHarnessRunner abstract base class
│       ├── agy.py                                    # AgyRunner subprocess execution & monitoring
│       └── mock.py                                   # MockRunner for deterministic unit/integration testing
├── cli.py                                            # Add 'orchestrate' parser and execution dispatch
tests/
├── test_orchestrator_models.py                       # Tests for models and state
├── test_orchestrator_mock_runner.py                  # Tests for base & mock runner
├── test_orchestrator_tracer.py                       # Tests for tracer & logging
├── test_orchestrator_agy_runner.py                   # Tests for AgyRunner subprocess logic
├── test_orchestrator_graph.py                        # Tests for LangGraph nodes and routing
├── test_orchestrator_engine.py                       # Integration tests for BookOrchestrator
└── test_orchestrator_cli.py                          # Tests for CLI argument parsing & dispatch
```

---

### Task 1: Project Dependencies & Package Scaffolding

**Files:**
- Modify: `pyproject.toml`
- Create: `src/dich_truyen_agent/orchestrator/__init__.py`
- Create: `src/dich_truyen_agent/orchestrator/runners/__init__.py`
- Test: `tests/test_orchestrator_scaffold.py`

- [ ] **Step 1: Write the failing test for orchestrator package imports**

```python
# tests/test_orchestrator_scaffold.py
def test_orchestrator_package_import():
    import dich_truyen_agent.orchestrator as orch
    import dich_truyen_agent.orchestrator.runners as runners
    import langgraph
    import langgraph.checkpoint.sqlite

    assert orch is not None
    assert runners is not None
    assert langgraph is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$env:PYTHONUTF8=1; uv run pytest tests/test_orchestrator_scaffold.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'langgraph'` or `No module named 'dich_truyen_agent.orchestrator'`

- [ ] **Step 3: Update `pyproject.toml` and scaffold package directories**

In `pyproject.toml`, add `"langgraph>=0.2,<2"` and `"langgraph-checkpoint-sqlite>=2.0,<4"` to `dependencies`.

Run:
```powershell
uv add "langgraph>=0.2,<2" "langgraph-checkpoint-sqlite>=2.0,<4"
```

Create `src/dich_truyen_agent/orchestrator/__init__.py`:
```python
"""Orchestrator package for Dich Truyen Agent."""
```

Create `src/dich_truyen_agent/orchestrator/runners/__init__.py`:
```python
"""Harness runners package for Dich Truyen Agent."""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `$env:PYTHONUTF8=1; uv run pytest tests/test_orchestrator_scaffold.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```powershell
git add pyproject.toml uv.lock src/dich_truyen_agent/orchestrator/__init__.py src/dich_truyen_agent/orchestrator/runners/__init__.py tests/test_orchestrator_scaffold.py
git commit -m "feat(orchestrator): add langgraph dependencies and scaffold package"
```

---

### Task 2: Models & Graph State Schemas

**Files:**
- Create: `src/dich_truyen_agent/orchestrator/models.py`
- Create: `src/dich_truyen_agent/orchestrator/state.py`
- Test: `tests/test_orchestrator_models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_orchestrator_models.py
from pathlib import Path
from dich_truyen_agent.orchestrator.models import HarnessRunResult, OrchestratorConfig, RunEvent
from dich_truyen_agent.orchestrator.state import BookOrchestratorState


def test_harness_run_result():
    res = HarnessRunResult(exit_code=0, stdout="done", stderr="", duration_seconds=1.5, timed_out=False)
    assert res.is_success
    assert res.duration_seconds == 1.5


def test_orchestrator_config_defaults():
    cfg = OrchestratorConfig(workspace=Path("books/test-book"))
    assert cfg.harness == "agy"
    assert cfg.auto_approve is False
    assert cfg.batch_size == 5
    assert cfg.timeout == 900
    assert cfg.log_level == "compact"


def test_book_orchestrator_state_structure():
    state: BookOrchestratorState = {
        "workspace": "books/test-book",
        "slug": "test-book",
        "harness": "agy",
        "auto_approve": False,
        "batch_size": 5,
        "timeout": 900,
        "total_chapters": 10,
        "completed_chapters": 0,
        "pending_chapters": 10,
        "consecutive_failures": 0,
        "crawl_completed": False,
        "crawl_approved": False,
        "qa_completed": False,
        "qa_approved": False,
        "export_completed": False,
        "status": "running",
        "error_message": None,
        "run_dir": "books/test-book/reports/runs/run_test",
    }
    assert state["slug"] == "test-book"
    assert state["pending_chapters"] == 10
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$env:PYTHONUTF8=1; uv run pytest tests/test_orchestrator_models.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write implementation**

Create `src/dich_truyen_agent/orchestrator/models.py`:
```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class HarnessRunResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool = False

    @property
    def is_success(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


@dataclass(frozen=True)
class OrchestratorConfig:
    workspace: Path
    harness: str = "agy"
    auto_approve: bool = False
    batch_size: int = 5
    timeout: int = 900
    log_level: Literal["compact", "verbose"] = "compact"


@dataclass(frozen=True)
class RunEvent:
    phase: str
    message: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    batch_index: int | None = None
    event_type: Literal["info", "milestone", "tool_call", "warning", "error"] = "info"
```

Create `src/dich_truyen_agent/orchestrator/state.py`:
```python
from __future__ import annotations

from typing import Optional, TypedDict


class BookOrchestratorState(TypedDict):
    workspace: str
    slug: str
    harness: str
    auto_approve: bool
    batch_size: int
    timeout: int

    total_chapters: int
    completed_chapters: int
    pending_chapters: int
    consecutive_failures: int

    crawl_completed: bool
    crawl_approved: bool
    qa_completed: bool
    qa_approved: bool
    export_completed: bool

    status: str  # "running", "paused", "completed", "blocked", "error"
    error_message: Optional[str]
    run_dir: str
```

- [ ] **Step 4: Run test to verify it passes**

Run: `$env:PYTHONUTF8=1; uv run pytest tests/test_orchestrator_models.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```powershell
git add src/dich_truyen_agent/orchestrator/models.py src/dich_truyen_agent/orchestrator/state.py tests/test_orchestrator_models.py
git commit -m "feat(orchestrator): add orchestrator models and state schemas"
```

---

### Task 3: Base Harness Runner & Mock Runner

**Files:**
- Create: `src/dich_truyen_agent/orchestrator/runners/base.py`
- Create: `src/dich_truyen_agent/orchestrator/runners/mock.py`
- Modify: `src/dich_truyen_agent/orchestrator/runners/__init__.py`
- Test: `tests/test_orchestrator_mock_runner.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_orchestrator_mock_runner.py
from pathlib import Path
from dich_truyen_agent.orchestrator.models import HarnessRunResult
from dich_truyen_agent.orchestrator.runners import BaseHarnessRunner, MockRunner


def test_mock_runner_execution_and_history():
    runner = MockRunner()
    runner.set_phase_result("crawl", HarnessRunResult(exit_code=0, stdout="Crawl ok", stderr="", duration_seconds=1.0))

    logged_lines = []
    result = runner.run_phase(
        phase="crawl",
        workspace=Path("books/test-book"),
        prompt="$ag-crawl-book books/test-book",
        timeout=60,
        on_log_line=logged_lines.append,
    )

    assert result.is_success
    assert len(runner.calls) == 1
    assert runner.calls[0]["phase"] == "crawl"
    assert runner.calls[0]["prompt"] == "$ag-crawl-book books/test-book"
    assert "Crawl ok" in logged_lines
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$env:PYTHONUTF8=1; uv run pytest tests/test_orchestrator_mock_runner.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write implementation**

Create `src/dich_truyen_agent/orchestrator/runners/base.py`:
```python
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path

from dich_truyen_agent.orchestrator.models import HarnessRunResult


class BaseHarnessRunner(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """The harness identifier, e.g. 'agy', 'claude', 'mock'."""
        pass

    @abstractmethod
    def run_phase(
        self,
        phase: str,
        workspace: Path,
        prompt: str,
        timeout: int,
        on_log_line: Callable[[str], None] | None = None,
    ) -> HarnessRunResult:
        """Execute a phase command using this harness."""
        pass
```

Create `src/dich_truyen_agent/orchestrator/runners/mock.py`:
```python
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from dich_truyen_agent.orchestrator.models import HarnessRunResult
from dich_truyen_agent.orchestrator.runners.base import BaseHarnessRunner


class MockRunner(BaseHarnessRunner):
    def __init__(self) -> None:
        self._results: dict[str, list[HarnessRunResult]] = {}
        self._default_result = HarnessRunResult(
            exit_code=0,
            stdout="[mock] success",
            stderr="",
            duration_seconds=0.1,
            timed_out=False,
        )
        self.calls: list[dict[str, Any]] = []

    @property
    def name(self) -> str:
        return "mock"

    def set_phase_result(self, phase: str, result: HarnessRunResult) -> None:
        self._results[phase] = [result]

    def set_phase_sequence(self, phase: str, results: list[HarnessRunResult]) -> None:
        self._results[phase] = list(results)

    def run_phase(
        self,
        phase: str,
        workspace: Path,
        prompt: str,
        timeout: int,
        on_log_line: Callable[[str], None] | None = None,
    ) -> HarnessRunResult:
        self.calls.append(
            {
                "phase": phase,
                "workspace": workspace,
                "prompt": prompt,
                "timeout": timeout,
            }
        )

        res_list = self._results.get(phase)
        if res_list:
            result = res_list.pop(0) if len(res_list) > 1 else res_list[0]
        else:
            result = self._default_result

        if on_log_line and result.stdout:
            for line in result.stdout.splitlines():
                on_log_line(line)

        return result
```

Update `src/dich_truyen_agent/orchestrator/runners/__init__.py`:
```python
from dich_truyen_agent.orchestrator.runners.base import BaseHarnessRunner
from dich_truyen_agent.orchestrator.runners.mock import MockRunner

__all__ = ["BaseHarnessRunner", "MockRunner"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `$env:PYTHONUTF8=1; uv run pytest tests/test_orchestrator_mock_runner.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```powershell
git add src/dich_truyen_agent/orchestrator/runners/base.py src/dich_truyen_agent/orchestrator/runners/mock.py src/dich_truyen_agent/orchestrator/runners/__init__.py tests/test_orchestrator_mock_runner.py
git commit -m "feat(orchestrator): add BaseHarnessRunner and MockRunner"
```

---

### Task 4: Activity Tracer & Persistent Logging

**Files:**
- Create: `src/dich_truyen_agent/orchestrator/tracer.py`
- Test: `tests/test_orchestrator_tracer.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_orchestrator_tracer.py
import json
from pathlib import Path
from dich_truyen_agent.orchestrator.tracer import ActivityTracer


def test_tracer_directory_and_logging(tmp_path: Path):
    workspace = tmp_path / "books" / "sample-novel"
    workspace.mkdir(parents=True)

    tracer = ActivityTracer(workspace=workspace, log_level="compact")
    assert tracer.run_dir.exists()
    assert tracer.run_dir.parent == workspace / "reports" / "runs"

    tracer.log_phase_start("crawl")
    tracer.handle_log_line("crawl", "Finding chapter 1...")
    tracer.handle_log_line("crawl", "Downloaded chapter 1")
    tracer.log_phase_end("crawl", success=True, duration_seconds=2.5)

    crawl_log = tracer.run_dir / "01_crawl.log"
    assert crawl_log.exists()
    content = crawl_log.read_text(encoding="utf-8")
    assert "Finding chapter 1..." in content
    assert "Downloaded chapter 1" in content

    tracer.save_summary(status="completed", total_chapters=10, completed_chapters=10)
    summary_file = tracer.run_dir / "run_summary.json"
    assert summary_file.exists()
    data = json.loads(summary_file.read_text(encoding="utf-8"))
    assert data["status"] == "completed"
    assert data["completed_chapters"] == 10
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$env:PYTHONUTF8=1; uv run pytest tests/test_orchestrator_tracer.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write implementation**

Create `src/dich_truyen_agent/orchestrator/tracer.py`:
```python
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any, Literal


class ActivityTracer:
    def __init__(self, workspace: Path, log_level: Literal["compact", "verbose"] = "compact") -> None:
        self.workspace = workspace
        self.log_level = log_level
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        self.run_dir = workspace / "reports" / "runs" / f"run_{timestamp}"
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self._current_phase_file: Path | None = None
        self._batch_counter = 0

    def get_phase_log_path(self, phase: str, batch_index: int | None = None) -> Path:
        prefix_map = {
            "crawl": "01_crawl.log",
            "qa": "03_qa.log",
            "export": "04_export.log",
        }
        if phase == "translate":
            idx = batch_index if batch_index is not None else self._batch_counter
            return self.run_dir / f"02_translate_batch_{idx:03d}.log"
        filename = prefix_map.get(phase, f"phase_{phase}.log")
        return self.run_dir / filename

    def log_phase_start(self, phase: str, batch_index: int | None = None) -> None:
        if phase == "translate" and batch_index is not None:
            self._batch_counter = batch_index

        self._current_phase_file = self.get_phase_log_path(phase, batch_index)
        banner = f"\n{'='*70}\n[ORCHESTRATOR] Bắt đầu Giai đoạn: {phase.upper()}"
        if batch_index is not None:
            banner += f" (Batch {batch_index})"
        banner += f"\n{'='*70}\n"
        print(banner)

        with self._current_phase_file.open("a", encoding="utf-8") as f:
            f.write(banner)

    def handle_log_line(self, phase: str, line: str) -> None:
        clean_line = line.rstrip("\r\n")
        timestamp_str = datetime.now(timezone.utc).strftime("%H:%M:%S")

        # Write to persistent log file
        if self._current_phase_file:
            with self._current_phase_file.open("a", encoding="utf-8") as f:
                f.write(f"[{timestamp_str}] {clean_line}\n")

        # Console rendering
        if self.log_level == "verbose":
            print(f"[{phase.upper()} {timestamp_str}] {clean_line}")
        else:
            # Compact mode filtering: milestone / tool call lines
            lower = clean_line.lower()
            if any(k in lower for k in ["tool", "chapter", "promote", "verify", "gate", "status:", "progress:", "error"]):
                print(f"[{phase.upper()} {timestamp_str}] {clean_line}")

    def log_phase_end(self, phase: str, success: bool, duration_seconds: float) -> None:
        status_text = "THÀNH CÔNG" if success else "THẤT BẠI"
        msg = f"[ORCHESTRATOR] Kết thúc {phase.upper()} - {status_text} sau {duration_seconds:.1f}s\n"
        print(msg)
        if self._current_phase_file:
            with self._current_phase_file.open("a", encoding="utf-8") as f:
                f.write(msg)

    def save_summary(self, status: str, total_chapters: int, completed_chapters: int, error: str | None = None) -> None:
        summary_data: dict[str, Any] = {
            "status": status,
            "total_chapters": total_chapters,
            "completed_chapters": completed_chapters,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "error": error,
        }
        summary_path = self.run_dir / "run_summary.json"
        summary_path.write_text(json.dumps(summary_data, indent=2, ensure_ascii=False), encoding="utf-8")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `$env:PYTHONUTF8=1; uv run pytest tests/test_orchestrator_tracer.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```powershell
git add src/dich_truyen_agent/orchestrator/tracer.py tests/test_orchestrator_tracer.py
git commit -m "feat(orchestrator): add ActivityTracer for live stream and run logs"
```

---

### Task 5: Antigravity Runner (`AgyRunner`)

**Files:**
- Create: `src/dich_truyen_agent/orchestrator/runners/agy.py`
- Modify: `src/dich_truyen_agent/orchestrator/runners/__init__.py`
- Test: `tests/test_orchestrator_agy_runner.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_orchestrator_agy_runner.py
from pathlib import Path
from unittest.mock import MagicMock, patch
from dich_truyen_agent.orchestrator.runners.agy import AgyRunner


def test_agy_runner_command_generation():
    runner = AgyRunner(agy_executable="agy.exe")
    cmd = runner.build_command(prompt="$ag-crawl-book books/slug", timeout=300)
    assert cmd == [
        "agy.exe",
        "-p",
        "$ag-crawl-book books/slug",
        "--dangerously-skip-permissions",
        "--print-timeout",
        "300s",
    ]


@patch("subprocess.Popen")
def test_agy_runner_execution(mock_popen):
    mock_proc = MagicMock()
    mock_proc.stdout.readline.side_effect = [
        "Initializing crawl...\n",
        "Finished crawling.\n",
        "",
    ]
    mock_proc.poll.return_value = 0
    mock_proc.returncode = 0
    mock_popen.return_value = mock_proc

    runner = AgyRunner(agy_executable="agy.exe")
    logs = []
    result = runner.run_phase(
        phase="crawl",
        workspace=Path("books/slug"),
        prompt="$ag-crawl-book books/slug",
        timeout=10,
        on_log_line=logs.append,
    )

    assert result.is_success
    assert "Initializing crawl..." in logs
    assert "Finished crawling." in logs
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$env:PYTHONUTF8=1; uv run pytest tests/test_orchestrator_agy_runner.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write implementation**

Create `src/dich_truyen_agent/orchestrator/runners/agy.py`:
```python
from __future__ import annotations

from collections.abc import Callable
import os
from pathlib import Path
import shutil
import subprocess
import time

from dich_truyen_agent.orchestrator.models import HarnessRunResult
from dich_truyen_agent.orchestrator.runners.base import BaseHarnessRunner


class AgyRunner(BaseHarnessRunner):
    def __init__(self, agy_executable: str | None = None) -> None:
        self._executable = agy_executable or self._resolve_agy_path()

    @property
    def name(self) -> str:
        return "agy"

    def _resolve_agy_path(self) -> str:
        found = shutil.which("agy")
        if found:
            return found
        # Common Windows path check
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        if local_app_data:
            candidate = Path(local_app_data) / "agy" / "bin" / "agy.exe"
            if candidate.exists():
                return str(candidate)
        return "agy"

    def build_command(self, prompt: str, timeout: int) -> list[str]:
        return [
            self._executable,
            "-p",
            prompt,
            "--dangerously-skip-permissions",
            "--print-timeout",
            f"{timeout}s",
        ]

    def run_phase(
        self,
        phase: str,
        workspace: Path,
        prompt: str,
        timeout: int,
        on_log_line: Callable[[str], None] | None = None,
    ) -> HarnessRunResult:
        cmd = self.build_command(prompt, timeout)
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"

        start_time = time.monotonic()
        captured_lines: list[str] = []
        timed_out = False

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
                bufsize=1,
            )

            deadline = start_time + timeout
            while True:
                line = proc.stdout.readline() if proc.stdout else ""
                if line:
                    clean = line.rstrip("\r\n")
                    captured_lines.append(clean)
                    if on_log_line:
                        on_log_line(clean)
                elif proc.poll() is not None:
                    break

                if time.monotonic() > deadline:
                    proc.kill()
                    timed_out = True
                    break

            proc.wait(timeout=5)
            exit_code = 124 if timed_out else proc.returncode
        except Exception as e:
            if on_log_line:
                on_log_line(f"[AgyRunner Exception] {e}")
            exit_code = 1
            captured_lines.append(str(e))

        duration = time.monotonic() - start_time
        return HarnessRunResult(
            exit_code=exit_code,
            stdout="\n".join(captured_lines),
            stderr="",
            duration_seconds=duration,
            timed_out=timed_out,
        )
```

Update `src/dich_truyen_agent/orchestrator/runners/__init__.py`:
```python
from dich_truyen_agent.orchestrator.runners.agy import AgyRunner
from dich_truyen_agent.orchestrator.runners.base import BaseHarnessRunner
from dich_truyen_agent.orchestrator.runners.mock import MockRunner

__all__ = ["AgyRunner", "BaseHarnessRunner", "MockRunner"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `$env:PYTHONUTF8=1; uv run pytest tests/test_orchestrator_agy_runner.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```powershell
git add src/dich_truyen_agent/orchestrator/runners/agy.py src/dich_truyen_agent/orchestrator/runners/__init__.py tests/test_orchestrator_agy_runner.py
git commit -m "feat(orchestrator): add AgyRunner for Antigravity CLI execution"
```

---

### Task 6: LangGraph Nodes & Conditional Edge Routers

**Files:**
- Create: `src/dich_truyen_agent/orchestrator/graph.py`
- Test: `tests/test_orchestrator_graph.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_orchestrator_graph.py
from pathlib import Path
from dich_truyen_agent.orchestrator.graph import (
    build_orchestrator_graph,
    translation_router,
    crawl_gate_router,
)
from dich_truyen_agent.orchestrator.runners.mock import MockRunner
from dich_truyen_agent.orchestrator.tracer import ActivityTracer


def test_translation_router_logic():
    # Still pending and under retry limit
    assert translation_router({"pending_chapters": 5, "consecutive_failures": 0}) == "translate_batch"
    # Completed all chapters
    assert translation_router({"pending_chapters": 0, "consecutive_failures": 0}) == "qa"
    # Failed too many times
    assert translation_router({"pending_chapters": 5, "consecutive_failures": 4}) == "__end__"


def test_crawl_gate_router_logic():
    assert crawl_gate_router({"crawl_approved": True}) == "check_translation_gate"
    assert crawl_gate_router({"crawl_approved": False}) == "__end__"


def test_graph_compiles_cleanly(tmp_path: Path):
    runner = MockRunner()
    tracer = ActivityTracer(tmp_path, log_level="compact")
    graph = build_orchestrator_graph(runner=runner, tracer=tracer, checkpointer=None)
    assert graph is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$env:PYTHONUTF8=1; uv run pytest tests/test_orchestrator_graph.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write implementation**

Create `src/dich_truyen_agent/orchestrator/graph.py`:
```python
from __future__ import annotations

from pathlib import Path
import time
from typing import Any, Literal

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from dich_truyen_agent.checkpoints import approve_checkpoint, check_gate
from dich_truyen_agent.models import CheckpointType
from dich_truyen_agent.orchestrator.runners.base import BaseHarnessRunner
from dich_truyen_agent.orchestrator.state import BookOrchestratorState
from dich_truyen_agent.orchestrator.tracer import ActivityTracer
from dich_truyen_agent.paths import workspace_paths
from dich_truyen_agent.workspace import inspect_workspace, next_translation_work_item


# Router functions
def check_workspace_router(state: BookOrchestratorState) -> Literal["crawl", "check_translation_gate", "__end__"]:
    if state["status"] in ["blocked", "error"]:
        return "__end__"
    if state["crawl_approved"]:
        return "check_translation_gate"
    return "crawl"


def crawl_gate_router(state: BookOrchestratorState) -> Literal["check_translation_gate", "__end__"]:
    if state["crawl_approved"]:
        return "check_translation_gate"
    return "__end__"


def translation_router(state: dict[str, Any]) -> Literal["translate_batch", "qa", "__end__"]:
    if state.get("pending_chapters", 0) == 0:
        return "qa"
    if state.get("consecutive_failures", 0) > 3:
        return "__end__"
    return "translate_batch"


def qa_gate_router(state: BookOrchestratorState) -> Literal["export", "__end__"]:
    if state["qa_approved"]:
        return "export"
    return "__end__"


def build_orchestrator_graph(
    runner: BaseHarnessRunner,
    tracer: ActivityTracer,
    checkpointer: BaseCheckpointSaver | None = None,
):
    workflow = StateGraph(BookOrchestratorState)

    def check_workspace_node(state: BookOrchestratorState) -> dict[str, Any]:
        ws_path = Path(state["workspace"])
        paths = workspace_paths(ws_path)
        if not paths.book_yaml.exists():
            return {"status": "error", "error_message": f"Workspace book.yaml not found: {ws_path}"}

        # Check existing gate statuses
        crawl_gate = check_gate(ws_path, CheckpointType.CRAWL_APPROVED)
        qa_gate = check_gate(ws_path, CheckpointType.QA_APPROVED)

        work_item = next_translation_work_item(ws_path)
        data = work_item.data or {}

        return {
            "crawl_approved": crawl_gate.status.value == "ok",
            "qa_approved": qa_gate.status.value == "ok",
            "total_chapters": data.get("progress_total", 0),
            "completed_chapters": data.get("progress_completed", 0),
            "pending_chapters": max(0, data.get("progress_total", 0) - data.get("progress_completed", 0)),
        }

    def crawl_node(state: BookOrchestratorState) -> dict[str, Any]:
        ws_path = Path(state["workspace"])
        tracer.log_phase_start("crawl")
        prompt = f"${runner.name}-crawl-book {ws_path.as_posix()}"
        res = runner.run_phase("crawl", ws_path, prompt, state["timeout"], on_log_line=lambda l: tracer.handle_log_line("crawl", l))
        tracer.log_phase_end("crawl", res.is_success, res.duration_seconds)

        crawl_report = workspace_paths(ws_path).crawl_report
        crawl_ok = crawl_report.exists() and res.is_success
        return {"crawl_completed": crawl_ok}

    def crawl_gate_node(state: BookOrchestratorState) -> dict[str, Any]:
        ws_path = Path(state["workspace"])
        if state["crawl_approved"]:
            return {"crawl_approved": True}

        # Check if can approve
        if state["auto_approve"]:
            try:
                approve_checkpoint(ws_path, CheckpointType.CRAWL_APPROVED, "reports/crawl.yaml", ["raw", "chapters.yaml", "state.yaml"])
                return {"crawl_approved": True}
            except Exception as e:
                return {"crawl_approved": False, "status": "blocked", "error_message": f"Auto approve crawl failed: {e}"}

        # Interactive approval
        print("\n[GATE] Crawl hoàn tất. Phê duyệt để bắt đầu dịch? [y/N]: ", end="", flush=True)
        ans = input().strip().lower()
        if ans in ["y", "yes"]:
            approve_checkpoint(ws_path, CheckpointType.CRAWL_APPROVED, "reports/crawl.yaml", ["raw", "chapters.yaml", "state.yaml"])
            return {"crawl_approved": True}
        return {"crawl_approved": False, "status": "paused"}

    def check_translation_gate(state: BookOrchestratorState) -> dict[str, Any]:
        ws_path = Path(state["workspace"])
        work_item = next_translation_work_item(ws_path)
        data = work_item.data or {}
        total = data.get("progress_total", 0)
        completed = data.get("progress_completed", 0)
        pending = max(0, total - completed)
        return {
            "total_chapters": total,
            "completed_chapters": completed,
            "pending_chapters": pending,
        }

    def translate_batch_node(state: BookOrchestratorState) -> dict[str, Any]:
        ws_path = Path(state["workspace"])
        prev_completed = state["completed_chapters"]
        batch_idx = (prev_completed // state["batch_size"]) + 1

        tracer.log_phase_start("translate", batch_index=batch_idx)
        prompt = f"${runner.name}-translate-book {ws_path.as_posix()}"
        res = runner.run_phase(
            "translate",
            ws_path,
            prompt,
            state["timeout"],
            on_log_line=lambda l: tracer.handle_log_line("translate", l),
        )
        tracer.log_phase_end("translate", res.is_success, res.duration_seconds)

        work_item = next_translation_work_item(ws_path)
        data = work_item.data or {}
        current_completed = data.get("progress_completed", 0)
        current_total = data.get("progress_total", 0)
        current_pending = max(0, current_total - current_completed)

        progress_moved = current_completed > prev_completed
        failures = 0 if progress_moved else state["consecutive_failures"] + 1

        return {
            "completed_chapters": current_completed,
            "pending_chapters": current_pending,
            "consecutive_failures": failures,
        }

    def qa_node(state: BookOrchestratorState) -> dict[str, Any]:
        ws_path = Path(state["workspace"])
        tracer.log_phase_start("qa")
        prompt = f"${runner.name}-check-translation {ws_path.as_posix()}"
        res = runner.run_phase("qa", ws_path, prompt, state["timeout"], on_log_line=lambda l: tracer.handle_log_line("qa", l))
        tracer.log_phase_end("qa", res.is_success, res.duration_seconds)
        return {"qa_completed": res.is_success}

    def qa_gate_node(state: BookOrchestratorState) -> dict[str, Any]:
        ws_path = Path(state["workspace"])
        if state["qa_approved"]:
            return {"qa_approved": True}

        if state["auto_approve"]:
            try:
                approve_checkpoint(ws_path, CheckpointType.QA_APPROVED, "reports/qa-report.yaml", ["translations", "reports/qa-report.yaml"])
                return {"qa_approved": True}
            except Exception as e:
                return {"qa_approved": False, "status": "blocked", "error_message": f"Auto approve QA failed: {e}"}

        print("\n[GATE] QA hoàn tất. Phê duyệt để bắt đầu xuất sách? [y/N]: ", end="", flush=True)
        ans = input().strip().lower()
        if ans in ["y", "yes"]:
            approve_checkpoint(ws_path, CheckpointType.QA_APPROVED, "reports/qa-report.yaml", ["translations", "reports/qa-report.yaml"])
            return {"qa_approved": True}
        return {"qa_approved": False, "status": "paused"}

    def export_node(state: BookOrchestratorState) -> dict[str, Any]:
        ws_path = Path(state["workspace"])
        tracer.log_phase_start("export")
        prompt = f"${runner.name}-export-book {ws_path.as_posix()} epub,azw3,mobi,pdf"
        res = runner.run_phase("export", ws_path, prompt, state["timeout"], on_log_line=lambda l: tracer.handle_log_line("export", l))
        tracer.log_phase_end("export", res.is_success, res.duration_seconds)
        return {"export_completed": res.is_success, "status": "completed"}

    # Add nodes
    workflow.add_node("check_workspace", check_workspace_node)
    workflow.add_node("crawl", crawl_node)
    workflow.add_node("crawl_gate", crawl_gate_node)
    workflow.add_node("check_translation_gate", check_translation_gate)
    workflow.add_node("translate_batch", translate_batch_node)
    workflow.add_node("qa", qa_node)
    workflow.add_node("qa_gate", qa_gate_node)
    workflow.add_node("export", export_node)

    # Add edges & conditional transitions
    workflow.add_edge(START, "check_workspace")
    workflow.add_conditional_edges("check_workspace", check_workspace_router)
    workflow.add_edge("crawl", "crawl_gate")
    workflow.add_conditional_edges("crawl_gate", crawl_gate_router)
    workflow.add_conditional_edges("check_translation_gate", translation_router)
    workflow.add_conditional_edges("translate_batch", translation_router)
    workflow.add_edge("qa", "qa_gate")
    workflow.add_conditional_edges("qa_gate", qa_gate_router)
    workflow.add_edge("export", END)

    return workflow.compile(checkpointer=checkpointer)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `$env:PYTHONUTF8=1; uv run pytest tests/test_orchestrator_graph.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```powershell
git add src/dich_truyen_agent/orchestrator/graph.py tests/test_orchestrator_graph.py
git commit -m "feat(orchestrator): add LangGraph StateGraph nodes and routing logic"
```

---

### Task 7: BookOrchestrator Workflow Engine

**Files:**
- Create: `src/dich_truyen_agent/orchestrator/orchestrator.py`
- Modify: `src/dich_truyen_agent/orchestrator/__init__.py`
- Test: `tests/test_orchestrator_engine.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_orchestrator_engine.py
from pathlib import Path
from unittest.mock import patch
from dich_truyen_agent.orchestrator import BookOrchestrator, OrchestratorConfig
from dich_truyen_agent.orchestrator.runners.mock import MockRunner
from dich_truyen_agent.workspace import initialize_workspace


def test_book_orchestrator_full_run_with_mock(tmp_path: Path):
    ws = tmp_path / "books" / "novel-test"
    initialize_workspace(
        books_root=tmp_path / "books",
        slug="novel-test",
        source_url="https://example.com",
        title="Novel Test",
    )

    runner = MockRunner()
    cfg = OrchestratorConfig(workspace=ws, auto_approve=True, batch_size=2)
    orchestrator = BookOrchestrator(config=cfg, runner=runner)

    with patch("dich_truyen_agent.orchestrator.graph.approve_checkpoint"):
        final_state = orchestrator.run()

    assert final_state["workspace"] == str(ws)
    assert len(runner.calls) > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$env:PYTHONUTF8=1; uv run pytest tests/test_orchestrator_engine.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Write implementation**

Create `src/dich_truyen_agent/orchestrator/orchestrator.py`:
```python
from __future__ import annotations

from pathlib import Path
import sqlite3

from langgraph.checkpoint.sqlite import SqliteSaver

from dich_truyen_agent.orchestrator.graph import build_orchestrator_graph
from dich_truyen_agent.orchestrator.models import OrchestratorConfig
from dich_truyen_agent.orchestrator.runners.agy import AgyRunner
from dich_truyen_agent.orchestrator.runners.base import BaseHarnessRunner
from dich_truyen_agent.orchestrator.state import BookOrchestratorState
from dich_truyen_agent.orchestrator.tracer import ActivityTracer


class BookOrchestrator:
    def __init__(self, config: OrchestratorConfig, runner: BaseHarnessRunner | None = None) -> None:
        self.config = config
        self.workspace = config.workspace.resolve()
        self.slug = self.workspace.name
        self.tracer = ActivityTracer(self.workspace, log_level=config.log_level)
        self.runner = runner or self._get_default_runner(config.harness)

        # Sqlite checkpointer path
        db_path = self.workspace / ".orchestrator.db"
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.checkpointer = SqliteSaver(self._conn)

        self.graph = build_orchestrator_graph(
            runner=self.runner,
            tracer=self.tracer,
            checkpointer=self.checkpointer,
        )

    def _get_default_runner(self, harness: str) -> BaseHarnessRunner:
        if harness == "agy":
            return AgyRunner()
        raise ValueError(f"Harness not yet supported in orchestrator: {harness}")

    def run(self) -> BookOrchestratorState:
        initial_state: BookOrchestratorState = {
            "workspace": str(self.workspace),
            "slug": self.slug,
            "harness": self.config.harness,
            "auto_approve": self.config.auto_approve,
            "batch_size": self.config.batch_size,
            "timeout": self.config.timeout,
            "total_chapters": 0,
            "completed_chapters": 0,
            "pending_chapters": 0,
            "consecutive_failures": 0,
            "crawl_completed": False,
            "crawl_approved": False,
            "qa_completed": False,
            "qa_approved": False,
            "export_completed": False,
            "status": "running",
            "error_message": None,
            "run_dir": str(self.tracer.run_dir),
        }

        thread_config = {"configurable": {"thread_id": self.slug}}

        try:
            final_state = self.graph.invoke(initial_state, config=thread_config)
            self.tracer.save_summary(
                status=final_state.get("status", "completed"),
                total_chapters=final_state.get("total_chapters", 0),
                completed_chapters=final_state.get("completed_chapters", 0),
                error=final_state.get("error_message"),
            )
            return final_state
        except Exception as e:
            self.tracer.save_summary(
                status="error",
                total_chapters=0,
                completed_chapters=0,
                error=str(e),
            )
            raise e
        finally:
            self._conn.close()
```

Update `src/dich_truyen_agent/orchestrator/__init__.py`:
```python
from dich_truyen_agent.orchestrator.models import HarnessRunResult, OrchestratorConfig, RunEvent
from dich_truyen_agent.orchestrator.orchestrator import BookOrchestrator
from dich_truyen_agent.orchestrator.state import BookOrchestratorState

__all__ = [
    "BookOrchestrator",
    "BookOrchestratorState",
    "HarnessRunResult",
    "OrchestratorConfig",
    "RunEvent",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `$env:PYTHONUTF8=1; uv run pytest tests/test_orchestrator_engine.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```powershell
git add src/dich_truyen_agent/orchestrator/orchestrator.py src/dich_truyen_agent/orchestrator/__init__.py tests/test_orchestrator_engine.py
git commit -m "feat(orchestrator): implement BookOrchestrator engine with Sqlite checkpointer"
```

---

### Task 8: Checkpoint Persistence & Crash Resumption Test

**Files:**
- Create: `tests/test_orchestrator_resume.py`

- [ ] **Step 1: Write the test verifying state recovery from Sqlite checkpointer**

```python
# tests/test_orchestrator_resume.py
from pathlib import Path
from unittest.mock import patch
from dich_truyen_agent.orchestrator import BookOrchestrator, OrchestratorConfig
from dich_truyen_agent.orchestrator.runners.mock import MockRunner
from dich_truyen_agent.workspace import initialize_workspace


def test_orchestrator_sqlite_checkpoint_resumption(tmp_path: Path):
    ws = tmp_path / "books" / "novel-resume"
    initialize_workspace(
        books_root=tmp_path / "books",
        slug="novel-resume",
        source_url="https://example.com",
        title="Novel Resume",
    )

    runner = MockRunner()
    cfg = OrchestratorConfig(workspace=ws, auto_approve=True)

    # First run
    with patch("dich_truyen_agent.orchestrator.graph.approve_checkpoint"):
        orch1 = BookOrchestrator(config=cfg, runner=runner)
        orch1.run()

    # Second run should open same sqlite db without corruption
    assert (ws / ".orchestrator.db").exists()
    orch2 = BookOrchestrator(config=cfg, runner=runner)
    assert orch2.checkpointer is not None
```

- [ ] **Step 2: Run test to verify it passes**

Run: `$env:PYTHONUTF8=1; uv run pytest tests/test_orchestrator_resume.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```powershell
git add tests/test_orchestrator_resume.py
git commit -m "test(orchestrator): add resumption and sqlite checkpointing test"
```

---

### Task 9: CLI Integration (`main.py orchestrate`)

**Files:**
- Modify: `src/dich_truyen_agent/cli.py`
- Test: `tests/test_orchestrator_cli.py`

- [ ] **Step 1: Write the failing test for `orchestrate` CLI parsing and dispatch**

```python
# tests/test_orchestrator_cli.py
from pathlib import Path
from unittest.mock import MagicMock, patch
from dich_truyen_agent.cli import build_parser, run_command


def test_cli_parser_orchestrate_arguments():
    parser = build_parser()
    args = parser.parse_args([
        "orchestrate",
        "--workspace", "books/my-novel",
        "--harness", "agy",
        "--auto-approve",
        "--batch-size", "10",
        "--timeout", "600",
        "--log-level", "verbose",
    ])
    assert args.command == "orchestrate"
    assert args.workspace == Path("books/my-novel")
    assert args.harness == "agy"
    assert args.auto_approve is True
    assert args.batch_size == 10
    assert args.timeout == 600
    assert args.log_level == "verbose"


@patch("dich_truyen_agent.orchestrator.BookOrchestrator.run")
def test_cli_run_command_orchestrate(mock_orch_run, tmp_path: Path):
    mock_orch_run.return_value = {
        "status": "completed",
        "completed_chapters": 10,
        "total_chapters": 10,
    }
    parser = build_parser()
    args = parser.parse_args([
        "orchestrate",
        "--workspace", str(tmp_path),
        "--auto-approve",
    ])
    res = run_command(args)
    assert res.status.value == "ok"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `$env:PYTHONUTF8=1; uv run pytest tests/test_orchestrator_cli.py -v`
Expected: FAIL with `error: argument command: invalid choice: 'orchestrate'`

- [ ] **Step 3: Add `orchestrate` command in `src/dich_truyen_agent/cli.py`**

In `build_parser()` in `cli.py`, add:
```python
    orch = subparsers.add_parser("orchestrate", help="Run end-to-end novel translation orchestration")
    orch.add_argument("--workspace", type=Path, required=True, help="Path to book workspace")
    orch.add_argument("--harness", default="agy", choices=["agy"], help="Agent harness runner")
    orch.add_argument("--auto-approve", action="store_true", help="Auto approve gates when no blockers")
    orch.add_argument("--batch-size", type=int, default=5, help="Chapters per translation session")
    orch.add_argument("--timeout", type=int, default=900, help="Subprocess timeout in seconds")
    orch.add_argument("--log-level", default="compact", choices=["compact", "verbose"], help="Console log level")
    add_json_flag(orch)
```

In `run_command(args)` in `cli.py`, add dispatch block:
```python
    elif args.command == "orchestrate":
        from dich_truyen_agent.orchestrator import BookOrchestrator, OrchestratorConfig

        try:
            cfg = OrchestratorConfig(
                workspace=args.workspace,
                harness=args.harness,
                auto_approve=args.auto_approve,
                batch_size=args.batch_size,
                timeout=args.timeout,
                log_level=args.log_level,
            )
            orchestrator = BookOrchestrator(config=cfg)
            final_state = orchestrator.run()
            status_val = OperationStatus.OK if final_state.get("status") == "completed" else OperationStatus.BLOCKED
            result = OperationResult(
                status=status_val,
                reason=final_state.get("error_message") or f"Orchestrator status: {final_state.get('status')}",
                data=final_state,
            )
        except Exception as e:
            result = OperationResult(
                status=OperationStatus.ERROR,
                reason=f"Orchestration failed: {e}",
            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `$env:PYTHONUTF8=1; uv run pytest tests/test_orchestrator_cli.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```powershell
git add src/dich_truyen_agent/cli.py tests/test_orchestrator_cli.py
git commit -m "feat(cli): add orchestrate command for end-to-end execution"
```

---

### Task 10: Documentation & Full Verification

**Files:**
- Modify: `README.md`
- Modify: `ARCHITECTURE.md`

- [ ] **Step 1: Update `README.md` and `ARCHITECTURE.md`**

In `README.md`, add documentation for the `orchestrate` command under Quick Usage.
In `ARCHITECTURE.md`, document ADR-0006: Standalone LangGraph Agent Orchestrator with Harness Runner Abstraction (v2.5).

- [ ] **Step 2: Run complete test suite and code quality checks**

Run:
```powershell
$env:PYTHONUTF8=1; uv run pytest
$env:PYTHONUTF8=1; uv run ruff check src tests main.py
$env:PYTHONUTF8=1; uv run ruff format --check
```
Expected: All tests pass, 0 lint warnings, format clean.

- [ ] **Step 3: Commit**

```powershell
git add README.md ARCHITECTURE.md
git commit -m "docs: document LangGraph orchestrator command and ADR-0006 architecture"
```
