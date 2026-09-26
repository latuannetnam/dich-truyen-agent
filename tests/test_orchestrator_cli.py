from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from orchestrator_support import (
    build_full_crawl_workspace,
    build_initialized_workspace,
    build_qa_approved_workspace,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
MAIN_PY = REPO_ROOT / "main.py"


def run_cli(*args: str, cwd: Path = REPO_ROOT) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, str(MAIN_PY), *args]
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["UV_CACHE_DIR"] = str(REPO_ROOT / ".uv-cache")
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_cli_legacy_command_exits_zero(tmp_path: Path) -> None:
    wf = build_initialized_workspace(tmp_path / "ws")
    proc = run_cli("inspect-workspace", "--workspace", str(wf.root))
    assert proc.returncode == 0
    assert "status:" in proc.stdout


def test_cli_orchestrate_completed_exits_zero(tmp_path: Path) -> None:
    wf = build_qa_approved_workspace(tmp_path / "ws")
    proc = run_cli(
        "orchestrate",
        "--workspace",
        str(wf.root),
        "--start-at",
        "qa",
        "--stop-after",
        "qa",
    )
    assert proc.returncode == 0
    assert "status: completed" in proc.stdout
    assert "span: qa -> qa" in proc.stdout


def test_cli_orchestrate_paused_exits_two(tmp_path: Path) -> None:
    wf = build_full_crawl_workspace(tmp_path / "ws")
    proc = run_cli(
        "orchestrate",
        "--workspace",
        str(wf.root),
        "--start-at",
        "crawl",
        "--stop-after",
        "crawl",
    )
    assert proc.returncode == 2
    assert "status: paused" in proc.stdout
    assert "--resume" in proc.stdout


def test_cli_orchestrate_blocked_reversed_spans_exits_three(tmp_path: Path) -> None:
    wf = build_initialized_workspace(tmp_path / "ws")
    proc = run_cli(
        "orchestrate",
        "--workspace",
        str(wf.root),
        "--start-at",
        "qa",
        "--stop-after",
        "crawl",
    )
    assert proc.returncode == 3
    assert "cannot precede start_at" in (proc.stdout + proc.stderr)


def test_cli_orchestrate_resume_conflict_exits_three(tmp_path: Path) -> None:
    wf = build_initialized_workspace(tmp_path / "ws")
    # Combining --resume with explicit start-at is disallowed
    proc = run_cli(
        "orchestrate",
        "--workspace",
        str(wf.root),
        "--resume",
        "--start-at",
        "translate",
    )
    assert proc.returncode == 3
    assert "cannot be combined" in (proc.stdout + proc.stderr).lower()


def test_cli_orchestrate_decision_without_resume_exits_three(tmp_path: Path) -> None:
    wf = build_initialized_workspace(tmp_path / "ws")
    proc = run_cli("orchestrate", "--workspace", str(wf.root), "--decision", "approve")
    assert proc.returncode == 3
    assert "--decision requires --resume" in (proc.stdout + proc.stderr)


def test_cli_orchestrate_json_output_mode(tmp_path: Path) -> None:
    wf = build_qa_approved_workspace(tmp_path / "ws")
    proc = run_cli(
        "orchestrate",
        "--workspace",
        str(wf.root),
        "--start-at",
        "qa",
        "--stop-after",
        "qa",
        "--json",
    )
    assert proc.returncode == 0
    data = json.loads(proc.stdout)
    assert data["status"] == "completed"
    assert data["selected_span"] == ["qa", "qa"]
    assert "run_id" in data


def test_cli_orchestrate_resume_flow(tmp_path: Path) -> None:
    wf = build_full_crawl_workspace(tmp_path / "ws")
    # 1. Run pauses on crawl approval
    proc1 = run_cli(
        "orchestrate",
        "--workspace",
        str(wf.root),
        "--start-at",
        "crawl",
        "--stop-after",
        "crawl",
    )
    assert proc1.returncode == 2

    # 2. Resume with plain resume (no decision) still pauses
    proc2 = run_cli("orchestrate", "--workspace", str(wf.root), "--resume")
    assert proc2.returncode == 2

    # 3. Resume with approve decision completes
    proc3 = run_cli(
        "orchestrate", "--workspace", str(wf.root), "--resume", "--decision", "approve"
    )
    assert proc3.returncode == 0
    assert "status: completed" in proc3.stdout
