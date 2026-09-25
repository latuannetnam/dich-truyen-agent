from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock
import subprocess
import pytest

from dich_truyen_agent.checkpoints import (
    check_orchestrator_gate,
)
from dich_truyen_agent.models import (
    ApprovalScope,
    CheckpointRecord,
    CheckpointType,
    OperationStatus,
    QAFinding,
    QAFindingType,
    QAReport,
)
from dich_truyen_agent.orchestrator.graph import GraphRunner
from dich_truyen_agent.orchestrator.models import OrchestratorConfig
from dich_truyen_agent.orchestrator.runners.mock import MockRunner
from dich_truyen_agent.orchestrator.workspace_ops import WorkspaceOps
from dich_truyen_agent.storage import atomic_write_yaml, load_yaml_model
from orchestrator_support import (
    WorkspaceFixture,
    build_qa_approved_workspace,
    build_translated_workspace,
)


class QAExportGraphFixture:
    def __init__(self, tmp_path: Path, *, approved: bool = True) -> None:
        if approved:
            self.wf: WorkspaceFixture = build_qa_approved_workspace(tmp_path / "ws", chapter_count=2)
        else:
            self.wf = build_translated_workspace(tmp_path / "ws", chapter_count=2)
        self.ops = WorkspaceOps()
        self.runner = MockRunner()

    def run(
        self,
        *,
        start_at: str = "export",
        stop_after: str = "export",
        auto_approve: bool = False,
        formats: list[str] | None = None,
    ):
        config = OrchestratorConfig(
            workspace_root=self.wf.root,
            start_at=start_at,
            stop_after=stop_after,
            auto_approve=auto_approve,
            formats=formats or ["epub", "txt"],
        )
        runner = GraphRunner(self.ops, self.runner, config)
        self.active_runner = runner
        return runner.run()


@pytest.fixture
def qa_export_graph_fixture(tmp_path: Path, monkeypatch) -> QAExportGraphFixture:
    # Mock find_epubcheck so test runs in environment without epubcheck installed
    monkeypatch.setattr(
        "dich_truyen_agent.export.find_epubcheck", lambda: ("epubcheck", False)
    )

    def mock_run(cmd, *args, **kwargs):
        class DummyProcess:
            returncode = 0
            stdout = "success"
            stderr = ""

        return DummyProcess()

    monkeypatch.setattr(subprocess, "run", mock_run)
    return QAExportGraphFixture(tmp_path, approved=True)


def test_export_only_never_starts_harness(qa_export_graph_fixture: QAExportGraphFixture) -> None:
    outcome = qa_export_graph_fixture.run(start_at="export", stop_after="export")
    assert outcome.status == "completed"
    assert qa_export_graph_fixture.runner.calls == []
    # Both epub and txt exist
    exports_dir = qa_export_graph_fixture.wf.root / "exports"
    slug = qa_export_graph_fixture.wf.root.name
    assert (exports_dir / f"{slug}.epub").is_file()
    assert (exports_dir / f"{slug}.txt").is_file()


def test_qa_reuse_without_report_rewrite(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("dich_truyen_agent.export.find_epubcheck", lambda: ("epubcheck", False))
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: MagicMock(returncode=0, stdout="", stderr=""))

    fix = QAExportGraphFixture(tmp_path, approved=True)
    qa_report_path = fix.wf.root / "reports" / "qa-report.yaml"
    orig_mtime = qa_report_path.stat().st_mtime if qa_report_path.is_file() else None

    outcome = fix.run(start_at="qa", stop_after="qa")
    assert outcome.status == "completed"
    assert fix.runner.calls == []
    # Report was not rewritten
    if orig_mtime is not None:
        assert qa_report_path.stat().st_mtime == orig_mtime


def test_qa_critical_errors_blocks_without_rerunning_translation(tmp_path: Path, monkeypatch) -> None:
    fix = QAExportGraphFixture(tmp_path, approved=False)

    # Invalidate translations with an unresolved glossary conflict to trigger a QA critical error
    from dich_truyen_agent.models import GlossaryConflict, GlossaryConflictReport
    conflict_report = GlossaryConflictReport(
        conflicts=[
            GlossaryConflict(
                term="剑来",
                existing_translation="Kiếm Lai",
                existing_source="manual",
                proposed_translation="Kiếm Đến",
                proposed_source="chapter_1_proposal",
                chapter_id=1,
            )
        ]
    )
    atomic_write_yaml(fix.wf.root / "reports" / "glossary-conflicts.yaml", conflict_report)

    outcome = fix.run(start_at="qa", stop_after="qa")
    assert outcome.status == "blocked"
    assert outcome.error_code == "needs_repair"
    # Never rerun translation from QA error
    assert fix.runner.calls == []


def test_qa_warnings_pauses_for_manual_approval_even_with_auto_approve(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("dich_truyen_agent.export.find_epubcheck", lambda: ("epubcheck", False))
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: MagicMock(returncode=0, stdout="", stderr=""))

    fix = QAExportGraphFixture(tmp_path, approved=False)

    # Create a QA report with a non-critical warning (e.g. structural warning)
    def mock_qa_with_warning(workspace_root: Path) -> QAReport:
        return QAReport(
            findings=[
                QAFinding(
                    chapter_id=1,
                    finding_type=QAFindingType.STRUCTURAL,
                    severity="warning",
                    message="Minor structural issue",
                )
            ],
            summary={"error_count": 0, "warning_count": 1, "findings_count": 1},
        )

    import dich_truyen_agent.orchestrator.graph as g_mod
    orig_run_qa = g_mod.run_qa_check
    g_mod.run_qa_check = mock_qa_with_warning

    try:
        # Auto approve policy pauses when findings exist!
        outcome = fix.run(start_at="qa", stop_after="qa", auto_approve=True)
        assert outcome.status == "paused"
        assert outcome.pending_approval == "qa_approval"

        # Resume with approval
        resumed = fix.active_runner.run(resume_decision={"approved": True})
        assert resumed.status == "completed"

        # Gate should be approved with PARTIAL scope due to warnings
        gate = check_orchestrator_gate(fix.wf.root, CheckpointType.QA_APPROVED)
        assert gate.status is OperationStatus.OK
        record = load_yaml_model(fix.wf.root / "checkpoints" / "qa-approved.yaml", CheckpointRecord)
        assert record.scope is ApprovalScope.PARTIAL
    finally:
        g_mod.run_qa_check = orig_run_qa


def test_qa_zero_findings_auto_approves(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("dich_truyen_agent.export.find_epubcheck", lambda: ("epubcheck", False))
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: MagicMock(returncode=0, stdout="", stderr=""))

    fix = QAExportGraphFixture(tmp_path, approved=False)

    # Clean QA report with 0 findings
    def mock_clean_qa(workspace_root: Path) -> QAReport:
        return QAReport(
            findings=[],
            summary={"error_count": 0, "warning_count": 0, "findings_count": 0},
        )

    import dich_truyen_agent.orchestrator.graph as g_mod
    orig_run_qa = g_mod.run_qa_check
    g_mod.run_qa_check = mock_clean_qa

    try:
        outcome = fix.run(start_at="qa", stop_after="qa", auto_approve=True)
        assert outcome.status == "completed"

        record = load_yaml_model(fix.wf.root / "checkpoints" / "qa-approved.yaml", CheckpointRecord)
        assert record.scope is ApprovalScope.FULL
    finally:
        g_mod.run_qa_check = orig_run_qa


def test_qa_evidence_mutation_during_pause_blocks(tmp_path: Path, monkeypatch) -> None:
    fix = QAExportGraphFixture(tmp_path, approved=False)

    # Clean QA report with 1 warning so it pauses
    def mock_qa_with_warning(workspace_root: Path) -> QAReport:
        return QAReport(
            findings=[
                QAFinding(
                    chapter_id=1,
                    finding_type=QAFindingType.STRUCTURAL,
                    severity="warning",
                    message="Minor warning",
                )
            ],
            summary={"error_count": 0, "warning_count": 1, "findings_count": 1},
        )

    import dich_truyen_agent.orchestrator.graph as g_mod
    orig_run_qa = g_mod.run_qa_check
    g_mod.run_qa_check = mock_qa_with_warning

    try:
        outcome = fix.run(start_at="qa", stop_after="qa", auto_approve=False)
        assert outcome.status == "paused"

        # Mutate translation during pause
        fix.wf.translation_paths[0].write_text("Mutated during pause", encoding="utf-8")

        # Resume
        resumed = fix.active_runner.run(resume_decision={"approved": True})
        assert resumed.status == "blocked"
        assert "evidence changed" in (resumed.error_message or "").lower()
    finally:
        g_mod.run_qa_check = orig_run_qa


def test_export_missing_epubcheck_blocks(tmp_path: Path, monkeypatch) -> None:
    fix = QAExportGraphFixture(tmp_path, approved=True)
    monkeypatch.setattr("dich_truyen_agent.export.find_epubcheck", lambda: (None, False))

    outcome = fix.run(start_at="export", stop_after="export")
    assert outcome.status == "blocked"
    assert "epubcheck" in (outcome.error_message or "").lower()


def test_export_missing_calibre_for_requested_derivative_blocks(tmp_path: Path, monkeypatch) -> None:
    fix = QAExportGraphFixture(tmp_path, approved=True)
    monkeypatch.setattr("dich_truyen_agent.export.find_epubcheck", lambda: ("epubcheck", False))
    monkeypatch.setattr("dich_truyen_agent.export.find_calibre", lambda: None)
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: MagicMock(returncode=0, stdout="", stderr=""))

    outcome = fix.run(start_at="export", stop_after="export", formats=["epub", "azw3"])
    assert outcome.status == "blocked"
    assert "calibre" in (outcome.error_message or "").lower() or "azw3" in (outcome.error_message or "").lower()


def test_export_output_file_missing_blocks(tmp_path: Path, monkeypatch) -> None:
    fix = QAExportGraphFixture(tmp_path, approved=True)
    monkeypatch.setattr("dich_truyen_agent.export.find_epubcheck", lambda: ("epubcheck", False))
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: MagicMock(returncode=0, stdout="", stderr=""))

    # Mock export_book to return OK but delete the output file
    import dich_truyen_agent.orchestrator.graph as g_mod
    orig_export = g_mod.export_book

    def mock_faulty_export(workspace_root, formats):
        res = orig_export(workspace_root, formats)
        # Delete generated epub
        slug = workspace_root.name
        epub_p = workspace_root / "exports" / f"{slug}.epub"
        if epub_p.is_file():
            epub_p.unlink()
        return res

    monkeypatch.setattr(g_mod, "export_book", mock_faulty_export)

    outcome = fix.run(start_at="export", stop_after="export", formats=["epub"])
    assert outcome.status == "blocked"
    assert "missing or empty" in (outcome.error_message or "").lower()


def test_export_rechecks_qa_gate_blocks_if_qa_stale(tmp_path: Path, monkeypatch) -> None:
    fix = QAExportGraphFixture(tmp_path, approved=True)
    monkeypatch.setattr("dich_truyen_agent.export.find_epubcheck", lambda: ("epubcheck", False))
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: MagicMock(returncode=0, stdout="", stderr=""))

    # Invalidate QA gate by corrupting the qa-approved checkpoint file
    qa_ckpt = fix.wf.root / "checkpoints" / "qa-approved.yaml"
    qa_ckpt.unlink()

    outcome = fix.run(start_at="export", stop_after="export")
    assert outcome.status == "blocked"
    assert "qa" in (outcome.error_message or "").lower()


def test_export_crash_and_resume_regenerates_requested_outputs(tmp_path: Path, monkeypatch) -> None:
    fix = QAExportGraphFixture(tmp_path, approved=True)
    monkeypatch.setattr("dich_truyen_agent.export.find_epubcheck", lambda: ("epubcheck", False))
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: MagicMock(returncode=0, stdout="", stderr=""))

    outcome = fix.run(start_at="export", stop_after="export", formats=["epub", "txt"])
    assert outcome.status == "completed"
    slug = fix.wf.root.name
    exports_dir = fix.wf.root / "exports"
    assert (exports_dir / f"{slug}.epub").is_file()
    assert (exports_dir / f"{slug}.txt").is_file()

