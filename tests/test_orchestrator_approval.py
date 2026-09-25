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
from orchestrator_support import build_initialized_workspace


class GraphApprovalFixture:
    def __init__(self, tmp_path: Path):
        self.wf = build_initialized_workspace(tmp_path / "ws", chapter_count=2)
        self.ops = WorkspaceOps()
        self.runner = MockRunner()
        self.calls: list[str] = []

        import dich_truyen_agent.orchestrator.graph as g_mod
        self.orig_approve = g_mod.approve_full_crawl

        def wrapped_approve(workspace_root, report):
            self.calls.append("approve_full_crawl")
            return self.orig_approve(workspace_root, report)

        g_mod.approve_full_crawl = wrapped_approve

    def cleanup(self):
        import dich_truyen_agent.orchestrator.graph as g_mod
        g_mod.approve_full_crawl = self.orig_approve

    def run(self, *, crawl_warning: bool = False, auto_approve: bool = False, stop_after: str = "crawl"):
        # Setup crawl output
        for i, raw_p in enumerate(self.wf.raw_paths, start=1):
            raw_p.write_text(f"Raw body {i}\n" * 10, encoding="utf-8")
        warnings = ["duplicate ordinal 1"] if crawl_warning else []
        rep = CrawlReport(
            discovered_count=2,
            selected_count=2,
            completed_count=2,
            failed_count=0,
            max_chapters=0,
            scope=ApprovalScope.FULL,
            active_profile_source="shared",
            warnings=warnings,
        )
        atomic_write_yaml(self.wf.report, rep)

        self.ops.run_crawl = MagicMock(return_value=OperationResult(status=OperationStatus.OK, reason="ok"))

        config = OrchestratorConfig(
            workspace_root=self.wf.root,
            start_at="crawl",
            stop_after=stop_after,
            auto_approve=auto_approve,
        )
        runner = GraphRunner(self.ops, self.runner, config)
        self.active_runner = runner
        return runner.run()


@pytest.fixture
def graph_fixture(tmp_path: Path):
    fix = GraphApprovalFixture(tmp_path)
    yield fix
    fix.cleanup()


def test_crawl_warning_auto_policy_pauses(graph_fixture: GraphApprovalFixture) -> None:
    outcome = graph_fixture.run(crawl_warning=True, auto_approve=True, stop_after="crawl")
    assert outcome.status == "paused"
    assert graph_fixture.calls.count("approve_full_crawl") == 0


def test_manual_approval_pauses_and_resumes_to_completion(graph_fixture: GraphApprovalFixture) -> None:
    # 1. First run without auto-approve pauses at interrupt
    first_outcome = graph_fixture.run(crawl_warning=False, auto_approve=False, stop_after="crawl")
    assert first_outcome.status == "paused"
    assert first_outcome.pending_approval == "crawl_approval"
    assert graph_fixture.calls.count("approve_full_crawl") == 0

    # 2. Resume with approval decision
    resumed_outcome = graph_fixture.active_runner.run(resume_decision={"approved": True})
    assert resumed_outcome.status == "completed"
    assert graph_fixture.calls.count("approve_full_crawl") == 1
    # Verify crawl-approved checkpoint is written
    assert (graph_fixture.wf.root / "checkpoints" / "crawl-approved.yaml").is_file()


def test_manual_approval_rejection_blocks(graph_fixture: GraphApprovalFixture) -> None:
    first_outcome = graph_fixture.run(crawl_warning=False, auto_approve=False, stop_after="crawl")
    assert first_outcome.status == "paused"

    # Resume with rejection
    resumed_outcome = graph_fixture.active_runner.run(resume_decision={"approved": False})
    assert resumed_outcome.status == "blocked"
    assert graph_fixture.calls.count("approve_full_crawl") == 0


def test_evidence_mutation_during_pause_forces_report_regeneration(graph_fixture: GraphApprovalFixture) -> None:
    first_outcome = graph_fixture.run(crawl_warning=False, auto_approve=False, stop_after="crawl")
    assert first_outcome.status == "paused"

    # Mutate a raw file while paused
    graph_fixture.wf.raw_paths[0].write_text("Mutated raw text body during pause", encoding="utf-8")

    # Resume with approval
    resumed_outcome = graph_fixture.active_runner.run(resume_decision={"approved": True})
    # Due to mutated evidence, approval did not write checkpoint directly
    assert graph_fixture.calls.count("approve_full_crawl") == 0
    assert resumed_outcome.status == "blocked"
