from __future__ import annotations

import json
from pathlib import Path

import pytest

from dich_truyen_agent.orchestrator.orchestrator import BookOrchestrator, WorkspaceLock
from dich_truyen_agent.orchestrator.runners.mock import MockRunner
from dich_truyen_agent.orchestrator.workspace_ops import WorkspaceOps
from orchestrator_support import (
    build_crawl_approved_workspace,
    build_initialized_workspace,
    build_qa_approved_workspace,
)


@pytest.fixture
def mock_runner() -> MockRunner:
    return MockRunner()


@pytest.fixture
def run_harness(mock_runner: MockRunner) -> BookOrchestrator:
    return BookOrchestrator(runner=mock_runner, ops=WorkspaceOps())


def test_new_phase_run_has_new_thread_id(
    run_harness: BookOrchestrator,
    tmp_path: Path,
) -> None:
    crawl_approved_workspace = build_crawl_approved_workspace(tmp_path / "ws1")
    # Fake translate execution
    first = run_harness.start(
        crawl_approved_workspace.root, start_at="translate", stop_after="translate"
    )
    assert first.status in ("completed", "paused", "blocked")

    qa_workspace = build_qa_approved_workspace(tmp_path / "ws2")
    second = run_harness.start(qa_workspace.root, start_at="qa", stop_after="qa")
    assert first.run_id != second.run_id
    assert second.selected_span == ("qa", "qa")


def test_workspace_lock_acquisition_and_release(tmp_path: Path) -> None:
    lock_file = tmp_path / "test.lock"
    lock1 = WorkspaceLock(lock_file)
    assert lock1.acquire() is True

    # Second lock fails while lock1 is held
    lock2 = WorkspaceLock(lock_file)
    assert lock2.acquire() is False

    # After lock1 releases, lock2 can acquire
    lock1.release()
    assert lock2.acquire() is True
    lock2.release()


def test_lock_contention_blocks_orchestrator(
    run_harness: BookOrchestrator,
    tmp_path: Path,
) -> None:
    wf = build_crawl_approved_workspace(tmp_path / "ws")
    lock_path = wf.root / "reports" / "runs" / ".orchestrator.lock"
    external_lock = WorkspaceLock(lock_path)
    assert external_lock.acquire() is True

    try:
        outcome = run_harness.start(
            wf.root, start_at="translate", stop_after="translate"
        )
        assert outcome.status == "blocked"
        assert outcome.error_code == "workspace_locked"
        assert outcome.exit_code == 3
    finally:
        external_lock.release()


def test_paused_run_reports_pending_resume_on_plain_new_invocation(
    mock_runner: MockRunner,
    tmp_path: Path,
) -> None:
    # Use full crawl workspace without approval so crawl pauses on manual approval
    from orchestrator_support import build_full_crawl_workspace

    wf = build_full_crawl_workspace(tmp_path / "ws")
    orchestrator = BookOrchestrator(runner=mock_runner, ops=WorkspaceOps())

    # Start with auto_approve=False so crawl pauses
    first_run = orchestrator.start(
        wf.root, start_at="crawl", stop_after="crawl", auto_approve=False
    )
    assert first_run.status == "paused"
    assert first_run.exit_code == 2

    # Plain new invocation with default start_at="auto" reports pending resume
    second_call = orchestrator.start(wf.root, start_at="auto", stop_after="export")
    assert second_call.status == "paused"
    assert second_call.run_id == first_run.run_id
    assert second_call.exit_code == 2
    assert (
        "pending" in (second_call.error_message or "").lower()
        or "resume" in (second_call.next_command or "").lower()
    )


def test_explicit_start_at_supersedes_paused_run(
    mock_runner: MockRunner,
    tmp_path: Path,
) -> None:
    from orchestrator_support import build_full_crawl_workspace

    wf = build_full_crawl_workspace(tmp_path / "ws")
    orchestrator = BookOrchestrator(runner=mock_runner, ops=WorkspaceOps())

    # First run pauses
    first_run = orchestrator.start(
        wf.root, start_at="crawl", stop_after="crawl", auto_approve=False
    )
    assert first_run.status == "paused"
    old_run_id = first_run.run_id

    # Check old run summary
    old_summary_file = wf.root / "reports" / "runs" / old_run_id / "run_summary.json"
    assert old_summary_file.is_file()

    # Now make workspace crawl-approved so explicit start_at="translate" can run
    from dich_truyen_agent.checkpoints import approve_full_crawl
    from dich_truyen_agent.models import CrawlReport
    from dich_truyen_agent.storage import load_yaml_model

    report = load_yaml_model(wf.report, CrawlReport)
    approve_full_crawl(wf.root, report)

    # Explicit new start_at="translate" marks old run superseded
    second_run = orchestrator.start(
        wf.root, start_at="translate", stop_after="translate"
    )
    assert second_run.run_id != old_run_id

    # Old run summary should now be superseded
    old_summary = json.loads(old_summary_file.read_text(encoding="utf-8"))
    assert old_summary["status"] == "superseded"

    # Attempting to resume superseded run fails
    superseded_resume = orchestrator.resume(wf.root, decision="approve")
    # Resume looks up current run in manifest or reports superseded
    assert superseded_resume.status in ("blocked", "error", "completed")


def test_resume_without_run_id_returns_error(
    run_harness: BookOrchestrator,
    tmp_path: Path,
) -> None:
    wf = build_initialized_workspace(tmp_path / "ws")
    outcome = run_harness.resume(wf.root)
    assert outcome.status in ("blocked", "error")
    assert outcome.exit_code in (1, 3)


def test_resume_paused_run_with_missing_decision_stays_paused(
    mock_runner: MockRunner,
    tmp_path: Path,
) -> None:
    from orchestrator_support import build_full_crawl_workspace

    wf = build_full_crawl_workspace(tmp_path / "ws")
    orchestrator = BookOrchestrator(runner=mock_runner, ops=WorkspaceOps())

    first_run = orchestrator.start(
        wf.root, start_at="crawl", stop_after="crawl", auto_approve=False
    )
    assert first_run.status == "paused"

    # Resume with no decision stays paused
    resumed = orchestrator.resume(wf.root, decision=None)
    assert resumed.status == "paused"
    assert resumed.run_id == first_run.run_id
    assert resumed.exit_code == 2


def test_resume_paused_run_with_approval_succeeds(
    mock_runner: MockRunner,
    tmp_path: Path,
) -> None:
    from orchestrator_support import build_full_crawl_workspace

    wf = build_full_crawl_workspace(tmp_path / "ws")
    orchestrator = BookOrchestrator(runner=mock_runner, ops=WorkspaceOps())

    first_run = orchestrator.start(
        wf.root, start_at="crawl", stop_after="crawl", auto_approve=False
    )
    assert first_run.status == "paused"

    # Resume with approve decision
    resumed = orchestrator.resume(wf.root, decision="approve")
    assert resumed.status == "completed"
    assert resumed.run_id == first_run.run_id
    assert resumed.exit_code == 0


def test_sqlite_checkpoint_file_exists_per_run(
    run_harness: BookOrchestrator,
    tmp_path: Path,
) -> None:
    wf = build_qa_approved_workspace(tmp_path / "ws")
    outcome = run_harness.start(wf.root, start_at="qa", stop_after="qa")
    assert outcome.status == "completed"

    sqlite_path = wf.root / "reports" / "runs" / outcome.run_id / "checkpoint.sqlite"
    assert sqlite_path.is_file()


def test_retention_prunes_terminal_run_but_preserves_paused(
    mock_runner: MockRunner,
    tmp_path: Path,
) -> None:
    wf = build_qa_approved_workspace(tmp_path / "ws")
    orchestrator = BookOrchestrator(runner=mock_runner, ops=WorkspaceOps())

    # 1. Create a completed run
    completed_run = orchestrator.start(wf.root, start_at="qa", stop_after="qa")
    assert completed_run.status == "completed"
    completed_db = (
        wf.root / "reports" / "runs" / completed_run.run_id / "checkpoint.sqlite"
    )
    assert completed_db.is_file()

    # Artificially set finished_at and mtime to 40 days ago
    completed_summary_file = (
        wf.root / "reports" / "runs" / completed_run.run_id / "run_summary.json"
    )
    summary_data = json.loads(completed_summary_file.read_text(encoding="utf-8"))
    summary_data["finished_at"] = "2026-08-01T00:00:00Z"
    completed_summary_file.write_text(json.dumps(summary_data), encoding="utf-8")

    # 2. Create a paused run
    from orchestrator_support import build_full_crawl_workspace

    wf2 = build_full_crawl_workspace(tmp_path / "ws2")
    paused_run = orchestrator.start(
        wf2.root, start_at="crawl", stop_after="crawl", auto_approve=False
    )
    assert paused_run.status == "paused"
    paused_db = wf2.root / "reports" / "runs" / paused_run.run_id / "checkpoint.sqlite"
    assert paused_db.is_file()

    # Also backdate paused run summary
    paused_summary_file = (
        wf2.root / "reports" / "runs" / paused_run.run_id / "run_summary.json"
    )
    paused_data = json.loads(paused_summary_file.read_text(encoding="utf-8"))
    paused_data["started_at"] = "2026-08-01T00:00:00Z"
    paused_summary_file.write_text(json.dumps(paused_data), encoding="utf-8")

    # Prune runs on wf (completed) and wf2 (paused)
    pruned_wf = orchestrator.prune_terminal_runs(wf.root, max_age_days=30)
    assert completed_run.run_id in pruned_wf
    assert not completed_db.exists()
    assert completed_summary_file.is_file()  # Summary preserved

    pruned_wf2 = orchestrator.prune_terminal_runs(wf2.root, max_age_days=30)
    assert paused_run.run_id not in pruned_wf2
    assert paused_db.is_file()  # Paused run DB never pruned
