from __future__ import annotations

import json
from pathlib import Path

from dich_truyen_agent.orchestrator.models import RunSummary
from dich_truyen_agent.orchestrator.tracer import ActivityTracer


def test_activity_tracer_writes_summary_atomically(tmp_path: Path) -> None:
    run_dir = tmp_path / "reports" / "runs" / "test-run-1"
    summary = RunSummary(
        run_id="test-run-1",
        status="running",
        start_at="crawl",
        stop_after="export",
        selected_span=("crawl", "export"),
        current_phase="crawl",
        requested_formats=["epub", "txt"],
        global_model="gemini-3.8-flash-high",
    )

    tracer = ActivityTracer(run_dir, summary)
    assert tracer.summary_file.is_file()

    # Verify initial summary content
    data = json.loads(tracer.summary_file.read_text(encoding="utf-8"))
    assert data["run_id"] == "test-run-1"
    assert data["status"] == "running"
    assert data["selected_span"] == ["crawl", "export"]
    assert data["global_model"] == "gemini-3.8-flash-high"


def test_activity_tracer_updates_status_and_timestamps(tmp_path: Path) -> None:
    run_dir = tmp_path / "reports" / "runs" / "test-run-2"
    summary = RunSummary(
        run_id="test-run-2",
        status="running",
        start_at="translate",
        stop_after="translate",
        selected_span=("translate", "translate"),
        current_phase="translate",
        requested_formats=["txt"],
    )

    tracer = ActivityTracer(run_dir, summary)
    assert tracer.summary.finished_at is None

    # Update progress
    tracer.update_status("running", current_phase="translate", completed_chapters=3, total_chapters=10)
    data = json.loads(tracer.summary_file.read_text(encoding="utf-8"))
    assert data["completed_chapters"] == 3
    assert data["total_chapters"] == 10
    assert data["finished_at"] is None

    # Complete run
    tracer.update_status("completed", effective_model="gemini-3.8-flash-high")
    data = json.loads(tracer.summary_file.read_text(encoding="utf-8"))
    assert data["status"] == "completed"
    assert data["effective_model"] == "gemini-3.8-flash-high"
    assert data["finished_at"] is not None


def test_activity_tracer_sanitizes_secrets_in_invocations(tmp_path: Path) -> None:
    run_dir = tmp_path / "reports" / "runs" / "test-run-3"
    summary = RunSummary(
        run_id="test-run-3",
        status="running",
        start_at="translate",
        stop_after="translate",
        selected_span=("translate", "translate"),
        current_phase="translate",
        requested_formats=["epub"],
    )

    tracer = ActivityTracer(run_dir, summary)
    tracer.record_invocation({
        "phase": "translate",
        "chapter_id": 1,
        "auth_header": "Bearer sk-proj-1234567890abcdefghijklmn",
        "prompt_summary": "Translate chapter 1 without raw text",
    })

    data = json.loads(tracer.summary_file.read_text(encoding="utf-8"))
    inv = data["invocations"][0]
    assert "sk-proj" not in inv["auth_header"]
    assert "[REDACTED]" in inv["auth_header"]
    assert inv["chapter_id"] == 1


def test_activity_tracer_allocates_distinct_log_paths(tmp_path: Path) -> None:
    run_dir = tmp_path / "reports" / "runs" / "test-run-4"
    summary = RunSummary(
        run_id="test-run-4",
        status="running",
        start_at="crawl",
        stop_after="crawl",
        selected_span=("crawl", "crawl"),
        current_phase="crawl",
        requested_formats=["epub"],
    )

    tracer = ActivityTracer(run_dir, summary)
    stdout_path, stderr_path = tracer.get_invocation_log_paths("ch0001_attempt1")
    assert stdout_path != stderr_path
    assert stdout_path.parent == run_dir / "logs"
    assert "ch0001_attempt1" in stdout_path.name
    assert "stdout" in stdout_path.name
    assert "stderr" in stderr_path.name
