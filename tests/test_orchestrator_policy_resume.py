from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from dich_truyen_agent.models import (
    ApprovalScope,
    CrawlReport,
    OperationResult,
    OperationStatus,
)
from dich_truyen_agent.orchestrator.models import OrchestratorConfig
from dich_truyen_agent.orchestrator.orchestrator import BookOrchestrator
from dich_truyen_agent.orchestrator.runners.mock import MockRunner
from dich_truyen_agent.orchestrator.workspace_ops import WorkspaceOps
from dich_truyen_agent.storage import atomic_write_yaml
from orchestrator_support import build_initialized_workspace


def test_paused_run_summary_contains_policy_and_resume_pins_it(tmp_path: Path) -> None:
    wf = build_initialized_workspace(
        tmp_path / "books" / "policy-book", chapter_count=2
    )

    for i, raw_p in enumerate(wf.raw_paths, start=1):
        raw_p.write_text(f"Raw body {i}\n" * 10, encoding="utf-8")
    rep = CrawlReport(
        discovered_count=2,
        selected_count=2,
        completed_count=2,
        failed_count=0,
        max_chapters=0,
        scope=ApprovalScope.FULL,
        active_profile_source="shared",
        warnings=[],
    )
    atomic_write_yaml(wf.report, rep)

    ops = WorkspaceOps()
    ops.run_crawl = MagicMock(
        return_value=OperationResult(status=OperationStatus.OK, reason="ok")
    )

    orchestrator = BookOrchestrator(runner=MockRunner(), ops=ops)
    config = OrchestratorConfig(
        workspace_root=wf.root,
        start_at="crawl",
        stop_after="crawl",
        scope_limit=2,
        formats=["epub", "azw3"],
        auto_approve=False,
        batch_size=3,
        timeout_seconds=1200,
        crawl_timeout_seconds=900,
        translation_timeout_seconds=900,
        qa_timeout_seconds=400,
        export_timeout_seconds=400,
        max_repair_attempts=2,
        max_chapter_attempts=4,
        global_model="test-global-model",
        translation_model="test-trans-model",
        allow_harness_permission_bypass=True,
    )

    first_outcome = orchestrator.start(config)
    assert first_outcome.status == "paused"

    # Verify run_summary.json contains run_policy
    run_dir = wf.root / "reports" / "runs" / first_outcome.run_id
    summary_file = run_dir / "run_summary.json"
    assert summary_file.is_file()
    summary = json.loads(summary_file.read_text(encoding="utf-8"))

    assert "run_policy" in summary
    policy = summary["run_policy"]
    assert policy["scope_limit"] == 2
    assert policy["formats"] == ["epub", "azw3"]
    assert policy["batch_size"] == 3
    assert policy["timeout_seconds"] == 1200
    assert policy["crawl_timeout_seconds"] == 900
    assert policy["translation_timeout_seconds"] == 900
    assert policy["qa_timeout_seconds"] == 400
    assert policy["export_timeout_seconds"] == 400
    assert policy["max_repair_attempts"] == 2
    assert policy["max_chapter_attempts"] == 4
    assert policy["global_model"] == "test-global-model"
    assert policy["translation_model"] == "test-trans-model"
    assert policy["allow_harness_permission_bypass"] is True

    # Resume the paused run
    resumed = orchestrator.resume(wf.root, decision="approve")
    assert resumed.status == "completed"


def test_resume_blocks_when_scope_digest_changes(tmp_path: Path) -> None:
    wf = build_initialized_workspace(
        tmp_path / "books" / "digest-mismatch-book", chapter_count=2
    )
    for i, raw_p in enumerate(wf.raw_paths, start=1):
        raw_p.write_text(f"Raw body {i}\n" * 10, encoding="utf-8")
    rep = CrawlReport(
        discovered_count=2,
        selected_count=2,
        completed_count=2,
        failed_count=0,
        max_chapters=0,
        scope=ApprovalScope.FULL,
        active_profile_source="shared",
        warnings=[],
    )
    atomic_write_yaml(wf.report, rep)

    ops = WorkspaceOps()
    ops.run_crawl = MagicMock(
        return_value=OperationResult(status=OperationStatus.OK, reason="ok")
    )

    orchestrator = BookOrchestrator(runner=MockRunner(), ops=ops)
    config = OrchestratorConfig(
        workspace_root=wf.root,
        start_at="crawl",
        stop_after="crawl",
        auto_approve=False,
    )

    first_outcome = orchestrator.start(config)
    assert first_outcome.status == "paused"

    # Inject source_scope_digest in run_summary
    run_dir = wf.root / "reports" / "runs" / first_outcome.run_id
    summary_file = run_dir / "run_summary.json"
    summary = json.loads(summary_file.read_text(encoding="utf-8"))
    summary["source_scope_digest"] = "expected_digest_123"
    summary_file.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    # When scope file has different digest or missing, resume blocks
    resumed = orchestrator.resume(wf.root, decision="approve")
    assert resumed.status == "blocked"
    assert "scope" in (resumed.error_message or "").lower()


def test_legacy_run_summary_without_run_policy_resumes_cleanly(tmp_path: Path) -> None:
    wf = build_initialized_workspace(
        tmp_path / "books" / "legacy-summary-book", chapter_count=2
    )
    for i, raw_p in enumerate(wf.raw_paths, start=1):
        raw_p.write_text(f"Raw body {i}\n" * 10, encoding="utf-8")
    rep = CrawlReport(
        discovered_count=2,
        selected_count=2,
        completed_count=2,
        failed_count=0,
        max_chapters=0,
        scope=ApprovalScope.FULL,
        active_profile_source="shared",
        warnings=[],
    )
    atomic_write_yaml(wf.report, rep)

    ops = WorkspaceOps()
    ops.run_crawl = MagicMock(
        return_value=OperationResult(status=OperationStatus.OK, reason="ok")
    )

    orchestrator = BookOrchestrator(runner=MockRunner(), ops=ops)
    config = OrchestratorConfig(
        workspace_root=wf.root,
        start_at="crawl",
        stop_after="crawl",
        auto_approve=False,
    )

    first_outcome = orchestrator.start(config)
    assert first_outcome.status == "paused"

    # Delete run_policy from summary to simulate legacy summary
    run_dir = wf.root / "reports" / "runs" / first_outcome.run_id
    summary_file = run_dir / "run_summary.json"
    summary = json.loads(summary_file.read_text(encoding="utf-8"))
    summary.pop("run_policy", None)
    summary_file.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    # Resume must still work using legacy fallback
    resumed = orchestrator.resume(wf.root, decision="approve")
    assert resumed.status == "completed"
