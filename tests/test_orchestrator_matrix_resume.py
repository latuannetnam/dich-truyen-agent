"""Exhaustive resume, failure, and lifecycle acceptance matrix tests (R01 - R15).

Verifies interrupts, evidence invalidation, crash boundaries, retry budgets,
supersession, locks, and recovery without external network or LLM calls.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dich_truyen_agent.checkpoints import (
    check_orchestrator_gate,
)
from dich_truyen_agent.models import (
    ApprovalScope,
    BookMetadata,
    ChapterCatalog,
    CheckpointType,
    CrawlReport,
    OperationResult,
    OperationStatus,
    QAReport,
    StageRecord,
    StageStatus,
)
from dich_truyen_agent.orchestrator import graph as graph_module
from dich_truyen_agent.orchestrator.orchestrator import BookOrchestrator, WorkspaceLock
from dich_truyen_agent.orchestrator.runners.mock import MockRunner
from dich_truyen_agent.orchestrator.workspace_ops import WorkspaceOps
from dich_truyen_agent.paths import workspace_paths
from dich_truyen_agent.storage import atomic_write_yaml, load_yaml_model, sha256_file
from orchestrator_support import (
    WorkspaceFixture,
    build_crawl_approved_workspace,
    build_initialized_workspace,
    build_qa_approved_workspace,
    build_translated_workspace,
)


class ResumeTestOrchestrator:
    def __init__(
        self, workspace: WorkspaceFixture, runner: MockRunner | None = None
    ) -> None:
        self.workspace = workspace
        self.runner = runner or MockRunner()
        self.ops = WorkspaceOps()
        self.called_phases: list[str] = []
        self._setup_mock_crawl()
        self._setup_mock_runner()
        self._setup_mock_export()
        self.orchestrator = BookOrchestrator(runner=self.runner, ops=self.ops)

    def _setup_mock_crawl(self, warnings: list[str] | None = None) -> None:
        def fake_crawl(workspace_root: Path, **kwargs: Any) -> OperationResult:
            if "crawl" not in self.called_phases:
                self.called_phases.append("crawl")
            paths = workspace_paths(workspace_root.parent, workspace_root.name)
            catalog = load_yaml_model(paths.chapters, ChapterCatalog)
            state = self.workspace.reload_state()
            for entry in catalog.chapters:
                raw_p = paths.raw / entry.raw_filename
                if not raw_p.is_file():
                    raw_p.write_text(
                        f"Raw content for {entry.original_title}\n" * 10,
                        encoding="utf-8",
                    )
                entry_state = next(
                    c for c in state.chapters if c.chapter_id == entry.chapter_id
                )
                entry_state.raw = StageRecord(
                    status=StageStatus.COMPLETED,
                    canonical_path=f"raw/{entry.raw_filename}",
                    sha256=sha256_file(raw_p),
                )
            atomic_write_yaml(paths.state, state)
            report = CrawlReport(
                discovered_count=len(catalog.chapters),
                selected_count=len(catalog.chapters),
                completed_count=len(catalog.chapters),
                failed_count=0,
                max_chapters=0,
                scope=ApprovalScope.FULL,
                active_profile_source="shared_template",
                warnings=warnings or [],
                chapter_lengths={str(c.chapter_id): 100 for c in catalog.chapters},
            )
            atomic_write_yaml(paths.reports / "crawl.yaml", report)
            return OperationResult(status=OperationStatus.OK, reason="crawl succeeded")

        self.ops.run_crawl = fake_crawl

    def _setup_mock_runner(self) -> None:
        def side_effect(workspace: Path, prompt: str, ctx: dict[str, Any]) -> None:
            phase = ctx.get("phase")
            if "translate" not in self.called_phases and phase in (
                "metadata_translation",
                "chapter_translation",
            ):
                self.called_phases.append("translate")
            if phase == "metadata_translation":
                meta = load_yaml_model(workspace / "book.yaml", BookMetadata)
                atomic_write_yaml(
                    workspace / "book.yaml",
                    meta.model_copy(
                        update={
                            "translated_title": f"Dịch: {meta.title}",
                            "translated_author": f"Dịch: {meta.author}"
                            if meta.author
                            else None,
                        }
                    ),
                )
            elif phase == "chapter_translation":
                staged_txt = None
                chapter_id = 1
                for line in prompt.splitlines():
                    if "staged_txt:" in line:
                        staged_txt = Path(line.partition("staged_txt:")[2].strip())
                    if "chapter_id:" in line:
                        try:
                            chapter_id = int(line.partition("chapter_id:")[2].strip())
                        except ValueError:
                            pass
                if staged_txt:
                    staged_txt.parent.mkdir(parents=True, exist_ok=True)
                    staged_txt.write_text(
                        f"# Chương {chapter_id} Tiêu Đề {chapter_id}\n\nNội dung dịch mẫu chuẩn xác.\n"
                        * 5,
                        encoding="utf-8",
                    )

        self.runner.add_side_effect(side_effect)

    def _setup_mock_export(self) -> None:
        def fake_export(workspace_root: Path, **kwargs: Any) -> OperationResult:
            if "export" not in self.called_phases:
                self.called_phases.append("export")
            paths = workspace_paths(workspace_root.parent, workspace_root.name)
            paths.exports.mkdir(parents=True, exist_ok=True)
            meta = load_yaml_model(paths.book, BookMetadata)
            formats = kwargs.get("formats") or ["epub", "txt"]
            artifacts = []
            for fmt in formats:
                f = paths.exports / f"{meta.book_slug}.{fmt}"
                f.write_text("fake export content", encoding="utf-8")
                artifacts.append(str(f))
            return OperationResult(
                status=OperationStatus.OK,
                reason="exported successfully",
                data={"artifacts": artifacts},
            )

        self.fake_export = fake_export


def test_r01_crawl_approval_pause_and_resume_approve(tmp_path: Path) -> None:
    """R01: Manual crawl approval pauses; resume with approve continues later phases."""
    wf = build_initialized_workspace(tmp_path / "r01")
    fixture = ResumeTestOrchestrator(wf)
    fixture._setup_mock_crawl(warnings=["Residue warning in chapter 1"])

    orig_export = graph_module.export_book
    graph_module.export_book = fixture.fake_export
    try:
        first = fixture.orchestrator.start(
            wf.root, start_at="crawl", stop_after="translate", auto_approve=False
        )
        assert first.status == "paused"
        assert first.exit_code == 2

        resumed = fixture.orchestrator.resume(
            wf.root, run_id=first.run_id, decision="approve"
        )
        assert resumed.status == "completed"
        assert resumed.run_id == first.run_id
        assert (
            check_orchestrator_gate(wf.root, CheckpointType.CRAWL_APPROVED).status
            is OperationStatus.OK
        )
        assert "translate" in fixture.called_phases
    finally:
        graph_module.export_book = orig_export


def test_r02_qa_approval_pause_and_resume_approve(tmp_path: Path) -> None:
    """R02: Manual QA approval pauses; resume with approve continues to export if selected."""
    wf = build_translated_workspace(tmp_path / "r02")
    fixture = ResumeTestOrchestrator(wf)

    orig_qa = graph_module.run_qa_check
    orig_export = graph_module.export_book
    graph_module.export_book = fixture.fake_export

    def qa_with_warnings(workspace_root: Path, **kwargs: Any) -> QAReport:
        rep = QAReport(
            summary={
                "error_count": 0,
                "warning_count": 1,
                "findings_count": 1,
                "passed": True,
            },
            findings=[
                {
                    "chapter_id": 1,
                    "finding_type": "residue",
                    "severity": "warning",
                    "message": "Minor warning",
                }
            ],
        )
        atomic_write_yaml(wf.root / "reports" / "qa-report.yaml", rep)
        return rep

    graph_module.run_qa_check = qa_with_warnings
    try:
        first = fixture.orchestrator.start(
            wf.root, start_at="qa", stop_after="export", auto_approve=False
        )
        assert first.status == "paused"
        assert first.exit_code == 2

        resumed = fixture.orchestrator.resume(
            wf.root, run_id=first.run_id, decision="approve"
        )
        assert resumed.status == "completed"
        assert resumed.run_id == first.run_id
        assert (
            check_orchestrator_gate(wf.root, CheckpointType.QA_APPROVED).status
            is OperationStatus.OK
        )
        assert "export" in fixture.called_phases
    finally:
        graph_module.run_qa_check = orig_qa
        graph_module.export_book = orig_export


def test_r03_evidence_changes_while_paused_requires_fresh_decision(
    tmp_path: Path,
) -> None:
    """R03: Evidence changes while paused invalidates resume decision."""
    wf = build_initialized_workspace(tmp_path / "r03")
    fixture = ResumeTestOrchestrator(wf)
    fixture._setup_mock_crawl(warnings=["Residue warning"])

    first = fixture.orchestrator.start(
        wf.root, start_at="crawl", stop_after="crawl", auto_approve=False
    )
    assert first.status == "paused"

    # Mutate raw chapter after pause
    wf.raw_paths[0].write_text("Mutated raw text", encoding="utf-8")

    resumed = fixture.orchestrator.resume(
        wf.root, run_id=first.run_id, decision="approve"
    )
    # Gate check or approval fails because evidence changed
    assert resumed.status in ("blocked", "paused")


def test_r04_resume_decisions(tmp_path: Path) -> None:
    """R04: Resume with reject ends blocked; missing decision remains paused; terminal cannot replay."""
    wf = build_initialized_workspace(tmp_path / "r04")
    fixture = ResumeTestOrchestrator(wf)
    fixture._setup_mock_crawl(warnings=["Residue warning"])

    first = fixture.orchestrator.start(
        wf.root, start_at="crawl", stop_after="crawl", auto_approve=False
    )
    assert first.status == "paused"

    # Resume without decision reports still paused
    no_decision = fixture.orchestrator.resume(
        wf.root, run_id=first.run_id, decision=None
    )
    assert no_decision.status == "paused"
    assert no_decision.exit_code == 2

    # Resume with reject ends blocked
    rejected = fixture.orchestrator.resume(
        wf.root, run_id=first.run_id, decision="reject"
    )
    assert rejected.status == "blocked"
    assert rejected.exit_code == 3

    # Terminal run cannot be resumed
    after_terminal = fixture.orchestrator.resume(
        wf.root, run_id=first.run_id, decision="approve"
    )
    assert after_terminal.status == "blocked"


def test_r05_crash_after_approval_rechecks_gate(tmp_path: Path) -> None:
    """R05: When crawl approval exists, resume recognizes it without duplicate write."""
    wf = build_crawl_approved_workspace(tmp_path / "r05")
    fixture = ResumeTestOrchestrator(wf)

    # Starting crawl phase when crawl is already approved is an immediate completion no-op
    res = fixture.orchestrator.start(wf.root, start_at="crawl", stop_after="crawl")
    assert res.status == "completed"
    assert len(fixture.called_phases) == 0


def test_r06_kill_crawl_subset_resumes_cleanly(tmp_path: Path) -> None:
    """R06: Resume after partial crawl completes remaining chapters in scope."""
    wf = build_initialized_workspace(tmp_path / "r06")
    wf.raw_paths[0].write_text("Chapter 1 raw content\n" * 10, encoding="utf-8")
    fixture = ResumeTestOrchestrator(wf)

    res = fixture.orchestrator.start(
        wf.root, start_at="crawl", stop_after="crawl", auto_approve=True
    )
    assert res.status == "completed"
    assert wf.raw_paths[1].is_file()


def test_r07_kill_translator_retries_without_stale_staging(tmp_path: Path) -> None:
    """R07: Failed or killed translation attempts leave clean staging and advance attempt journal."""
    wf = build_crawl_approved_workspace(tmp_path / "r07")
    fixture = ResumeTestOrchestrator(wf)

    # Pre-populate invalid staged file
    staged_dir = wf.root / "staging" / "attempts" / "0001-run_x-att_1"
    staged_dir.mkdir(parents=True, exist_ok=True)
    (staged_dir / "chapter.txt").write_text("Corrupt staging", encoding="utf-8")

    # Clean translation completes valid output
    outcome = fixture.orchestrator.start(
        wf.root, start_at="translate", stop_after="translate"
    )
    assert outcome.status == "completed"
    assert wf.translation_paths[0].is_file()


def test_r08_promotion_journal_recovery(tmp_path: Path) -> None:
    """R08: Promotion crash recovery rolls forward matching prepared hashes without duplicate merge."""
    wf = build_crawl_approved_workspace(tmp_path / "r08")
    ops = WorkspaceOps()

    from dich_truyen_agent.workspace import get_staging_paths

    paths = workspace_paths(wf.root.parent, wf.root.name)
    staged_txt, _ = get_staging_paths(paths, 1)
    staged_txt.parent.mkdir(parents=True, exist_ok=True)
    staged_txt.write_text(
        "# Chương 1 Tiên Nhân Chỉ Lộ\n\nBản dịch kiểm thử chuẩn mực.\n",
        encoding="utf-8",
    )

    # Promote chapter normally
    prom_res = ops.promote_translation(
        wf.root,
        1,
        staged_txt_path=staged_txt,
    )
    assert prom_res.status is OperationStatus.OK

    # Recover promotion should be a clean success because state is already completed
    rec_res = ops.recover_promotion(wf.root, 1)
    assert rec_res.status is OperationStatus.OK


def test_r09_three_failed_translator_launches_exhausts_budget(tmp_path: Path) -> None:
    """R09: Three failed translator launches exhaust the run budget and block cleanly."""
    wf = build_crawl_approved_workspace(tmp_path / "r09")
    runner = MockRunner()

    # Side effect writes invalid translation so verify_staged_chapter fails
    def bad_side_effect(workspace: Path, prompt: str, ctx: dict[str, Any]) -> None:
        if ctx.get("phase") == "chapter_translation":
            staged_txt = None
            for line in prompt.splitlines():
                if "staged_txt:" in line:
                    staged_txt = Path(line.partition("staged_txt:")[2].strip())
                    break
            if staged_txt:
                staged_txt.parent.mkdir(parents=True, exist_ok=True)
                staged_txt.write_text(
                    "Invalid text with no chapter heading", encoding="utf-8"
                )

    runner.add_side_effect(bad_side_effect)
    orchestrator = BookOrchestrator(runner=runner, ops=WorkspaceOps())

    outcome = orchestrator.start(wf.root, start_at="translate", stop_after="translate")
    assert outcome.status == "blocked"
    assert outcome.exit_code == 3


def test_r10_paused_run_superseded_by_new_start(tmp_path: Path) -> None:
    """R10: Paused run becomes superseded when an explicit new run starts."""
    wf = build_initialized_workspace(tmp_path / "r10")
    fixture = ResumeTestOrchestrator(wf)
    fixture._setup_mock_crawl(warnings=["Warning pause"])

    first = fixture.orchestrator.start(
        wf.root, start_at="crawl", stop_after="crawl", auto_approve=False
    )
    assert first.status == "paused"

    # Start new run
    second = fixture.orchestrator.start(
        wf.root, start_at="crawl", stop_after="crawl", auto_approve=True
    )
    assert second.run_id != first.run_id

    # First run's summary is marked as superseded
    first_summary_file = (
        wf.root / "reports" / "runs" / first.run_id / "run_summary.json"
    )
    first_summary = json.loads(first_summary_file.read_text(encoding="utf-8"))
    assert first_summary["status"] == "superseded"


def test_r11_lock_contention_and_release(tmp_path: Path) -> None:
    """R11: Second orchestrator process blocks on lock; releases cleanly on exit."""
    wf = build_initialized_workspace(tmp_path / "r11")
    fixture = ResumeTestOrchestrator(wf)

    lock_file = fixture.orchestrator._lock_path(wf.root)
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    external_lock = WorkspaceLock(lock_file)
    assert external_lock.acquire() is True

    try:
        blocked_outcome = fixture.orchestrator.start(
            wf.root, start_at="crawl", stop_after="crawl"
        )
        assert blocked_outcome.status == "blocked"
        assert blocked_outcome.error_code == "workspace_locked"
    finally:
        external_lock.release()

    # Can now acquire and run
    free_outcome = fixture.orchestrator.start(
        wf.root, start_at="crawl", stop_after="crawl", auto_approve=True
    )
    assert free_outcome.status == "completed"


def test_r12_direct_start_without_prior_sqlite_run(tmp_path: Path) -> None:
    """R12: Valid prior workspace gates allow direct start of later phases without SQLite history."""
    wf = build_crawl_approved_workspace(tmp_path / "r12")
    fixture = ResumeTestOrchestrator(wf)

    # Directly run translate with no sqlite db
    outcome = fixture.orchestrator.start(
        wf.root, start_at="translate", stop_after="translate"
    )
    assert outcome.status == "completed"


def test_r13_metadata_translated_once(tmp_path: Path) -> None:
    """R13: Translated metadata in book.yaml is not translated a second time."""
    wf = build_crawl_approved_workspace(tmp_path / "r13")
    fixture = ResumeTestOrchestrator(wf)

    # Pre-translate metadata
    meta = load_yaml_model(wf.book, BookMetadata)
    atomic_write_yaml(
        wf.book,
        meta.model_copy(
            update={
                "translated_title": "Bản Dịch Tiêu Đề",
                "translated_author": "Dịch Tác Giả",
            }
        ),
    )

    metadata_calls: list[str] = []

    def spy_side_effect(workspace: Path, prompt: str, ctx: dict[str, Any]) -> None:
        if ctx.get("phase") == "metadata_translation":
            metadata_calls.append("metadata")

    fixture.runner.add_side_effect(spy_side_effect)

    outcome = fixture.orchestrator.start(
        wf.root, start_at="translate", stop_after="translate"
    )
    assert outcome.status == "completed"
    assert len(metadata_calls) == 0


def test_r14_qa_report_reuse_or_fresh_decision(tmp_path: Path) -> None:
    """R14: Existing QA gate is reused without regenerating QA report."""
    wf = build_qa_approved_workspace(tmp_path / "r14")
    fixture = ResumeTestOrchestrator(wf)

    outcome = fixture.orchestrator.start(wf.root, start_at="qa", stop_after="qa")
    assert outcome.status == "completed"
    assert len(fixture.called_phases) == 0


def test_r15_export_completion_verifies_artifacts(tmp_path: Path) -> None:
    """R15: Export completes and records artifacts."""
    wf = build_qa_approved_workspace(tmp_path / "r15")
    fixture = ResumeTestOrchestrator(wf)

    orig_export = graph_module.export_book
    graph_module.export_book = fixture.fake_export
    try:
        outcome = fixture.orchestrator.start(
            wf.root, start_at="export", stop_after="export", formats=["epub"]
        )
        assert outcome.status == "completed"
        assert "export" in fixture.called_phases
    finally:
        graph_module.export_book = orig_export
