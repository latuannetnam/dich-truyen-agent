from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from dich_truyen_agent.models import (
    ApprovalScope,
    CrawlReport,
    OperationResult,
    OperationStatus,
)
from dich_truyen_agent.orchestrator.graph import GraphRunner
from dich_truyen_agent.orchestrator.models import OrchestratorConfig
from dich_truyen_agent.orchestrator.runners.mock import MockRunner
from dich_truyen_agent.orchestrator.workspace_ops import WorkspaceOps
from dich_truyen_agent.storage import atomic_write_yaml
from orchestrator_support import (
    build_crawl_approved_workspace,
    build_initialized_workspace,
)


@pytest.fixture
def mock_runner() -> MockRunner:
    return MockRunner()


def test_normal_crawl_makes_no_agent_calls(tmp_path: Path, mock_runner: MockRunner) -> None:
    wf = build_initialized_workspace(tmp_path / "ws", chapter_count=2)
    ops = WorkspaceOps()

    # Mock crawl execution succeeding
    def fake_crawl(workspace_root: Path, **kwargs) -> OperationResult:
        # Simulate crawl writing raw files
        for i, raw_p in enumerate(wf.raw_paths, start=1):
            raw_p.write_text(f"Raw body {i}\n" * 10, encoding="utf-8")
        wf.promote_first_translation()  # just to write state
        # populate report
        rep = CrawlReport(
            discovered_count=2,
            selected_count=2,
            completed_count=2,
            failed_count=0,
            max_chapters=0,
            scope=ApprovalScope.FULL,
            active_profile_source="shared",
        )
        atomic_write_yaml(wf.report, rep)
        return OperationResult(status=OperationStatus.OK, reason="crawl succeeded")

    ops.run_crawl = fake_crawl

    config = OrchestratorConfig(
        workspace_root=wf.root,
        start_at="crawl",
        stop_after="crawl",
        auto_approve=True,
    )
    graph_runner = GraphRunner(ops, mock_runner, config)
    outcome = graph_runner.run()

    # No agent calls on normal crawl
    assert len(mock_runner.calls) == 0
    assert outcome.status == "completed"


def test_nonempty_complete_raw_skips_download_and_goes_to_report(tmp_path: Path, mock_runner: MockRunner) -> None:
    wf = build_crawl_approved_workspace(tmp_path / "ws", chapter_count=2)
    # Remove approval to test re-entering crawl
    (wf.root / "checkpoints" / "crawl-approved.yaml").unlink()

    ops = WorkspaceOps()
    crawl_called = False

    def fake_crawl(workspace_root: Path, **kwargs) -> OperationResult:
        nonlocal crawl_called
        crawl_called = True
        return OperationResult(status=OperationStatus.OK, reason="crawled")

    ops.run_crawl = fake_crawl

    config = OrchestratorConfig(
        workspace_root=wf.root,
        start_at="crawl",
        stop_after="crawl",
        auto_approve=True,
    )
    graph_runner = GraphRunner(ops, mock_runner, config)
    outcome = graph_runner.run()

    # Download was skipped because all raw files were already ready!
    assert crawl_called is False
    assert outcome.status == "completed"


def test_profile_failure_triggers_automatic_repair_and_retry(tmp_path: Path, mock_runner: MockRunner) -> None:
    wf = build_initialized_workspace(tmp_path / "ws", chapter_count=2)
    ops = WorkspaceOps()

    crawl_attempts = 0

    def fake_crawl(workspace_root: Path, **kwargs) -> OperationResult:
        nonlocal crawl_attempts
        crawl_attempts += 1
        if crawl_attempts == 1:
            return OperationResult(
                status=OperationStatus.BLOCKED,
                reason="profile selector failed: index selector returned zero chapters",
            )
        # 2nd crawl after repair succeeds
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
        )
        atomic_write_yaml(wf.report, rep)
        return OperationResult(status=OperationStatus.OK, reason="crawl succeeded after repair")

    ops.run_crawl = fake_crawl

    # Agent side effect: propose a valid candidate profile file
    def agent_side_effect(workspace: Path, prompt: str, ctx: dict) -> None:
        # Extract candidate path from prompt
        for line in prompt.splitlines():
            if "candidate path:" in line:
                cand_path = Path(line.partition("candidate path:")[2].strip())
                cand_path.parent.mkdir(parents=True, exist_ok=True)
                valid_profile_yaml = (
                    "schema_version: 1\n"
                    "domain: example.com\n"
                    "index:\n"
                    "  chapter_link_selector: '.chapters a'\n"
                    "chapter:\n"
                    "  title_selector: 'h1'\n"
                    "  content_selector: '.content'\n"
                    "encoding:\n"
                    "  index: 'utf-8'\n"
                    "  chapter: 'utf-8'\n"
                    "validation:\n"
                    "  min_chapter_characters: 10\n"
                )
                cand_path.write_text(valid_profile_yaml, encoding="utf-8")

    mock_runner.add_side_effect(agent_side_effect)

    # Mock probe to return OK for the candidate
    import dich_truyen_agent.crawl_probe as probe_module
    import dich_truyen_agent.orchestrator.graph as graph_module
    orig_probe_graph = graph_module.probe_crawl_profile
    orig_probe_module = probe_module.probe_crawl_profile
    mock_probe = MagicMock(return_value=OperationResult(status=OperationStatus.OK, reason="probe passed"))
    graph_module.probe_crawl_profile = mock_probe
    probe_module.probe_crawl_profile = mock_probe

    try:
        config = OrchestratorConfig(
            workspace_root=wf.root,
            start_at="crawl",
            stop_after="crawl",
            auto_approve=True,
        )
        graph_runner = GraphRunner(ops, mock_runner, config)
        outcome = graph_runner.run()

        assert crawl_attempts == 2
        assert len(mock_runner.calls) == 1
        assert mock_runner.calls[0].phase == "profile_repair"
        # Local override profile was installed
        assert (wf.root / "crawl-profile.yaml").is_file()
        assert outcome.status == "completed"
    finally:
        graph_module.probe_crawl_profile = orig_probe_graph
        probe_module.probe_crawl_profile = orig_probe_module


def test_repair_budget_exhaustion_stops_at_blocked(tmp_path: Path, mock_runner: MockRunner) -> None:
    wf = build_initialized_workspace(tmp_path / "ws", chapter_count=2)
    ops = WorkspaceOps()

    # Always fail crawl with selector error
    ops.run_crawl = lambda *args, **kwargs: OperationResult(
        status=OperationStatus.BLOCKED,
        reason="profile selector broken",
    )

    # Agent does not write valid candidate
    config = OrchestratorConfig(
        workspace_root=wf.root,
        start_at="crawl",
        stop_after="crawl",
        auto_approve=True,
    )
    graph_runner = GraphRunner(ops, mock_runner, config)
    outcome = graph_runner.run()

    # Blocked after failing to get candidate / exhausting budget
    assert outcome.status == "blocked"


def test_unauthorized_workspace_mutation_by_repair_agent_blocks(tmp_path: Path, mock_runner: MockRunner) -> None:
    wf = build_initialized_workspace(tmp_path / "ws", chapter_count=2)
    ops = WorkspaceOps()
    ops.run_crawl = lambda *args, **kwargs: OperationResult(
        status=OperationStatus.BLOCKED,
        reason="profile selector broken",
    )

    # Agent mutates book.yaml illegally
    def bad_agent_side_effect(workspace: Path, prompt: str, ctx: dict) -> None:
        (workspace / "book.yaml").write_text("corrupted content", encoding="utf-8")
        for line in prompt.splitlines():
            if "candidate path:" in line:
                cand_path = Path(line.partition("candidate path:")[2].strip())
                cand_path.parent.mkdir(parents=True, exist_ok=True)
                cand_path.write_text("dummy", encoding="utf-8")

    mock_runner.add_side_effect(bad_agent_side_effect)

    config = OrchestratorConfig(
        workspace_root=wf.root,
        start_at="crawl",
        stop_after="crawl",
        auto_approve=True,
    )
    graph_runner = GraphRunner(ops, mock_runner, config)
    outcome = graph_runner.run()

    assert outcome.status == "blocked"
    assert "unauthorized workspace mutation" in (outcome.error_message or "").lower()
