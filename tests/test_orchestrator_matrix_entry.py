"""Exhaustive entry and phase span acceptance matrix tests (E01 - E15).

Verifies all ten valid explicit phase spans, six reversed invalid spans,
four auto endpoints, and deterministic domain prerequisites without network/LLM calls.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
import pytest

from dich_truyen_agent.models import (
    ApprovalScope,
    BookMetadata,
    ChapterCatalog,
    CrawlReport,
    OperationResult,
    OperationStatus,
    StageRecord,
    StageStatus,
)
from dich_truyen_agent.orchestrator import graph as graph_module
from dich_truyen_agent.orchestrator.models import RunOutcome
from dich_truyen_agent.orchestrator.orchestrator import BookOrchestrator
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


class EntryTestOrchestrator:
    """Orchestrator test harness tracking which graph nodes/phases are executed."""

    def __init__(
        self, workspace: WorkspaceFixture, runner: MockRunner | None = None
    ) -> None:
        self.workspace = workspace
        self.runner = runner or MockRunner()
        self.ops = WorkspaceOps()
        self.called_phases: list[str] = []
        self._setup_mock_crawl()
        self._setup_mock_runner()
        self._setup_mock_translate()
        self.orchestrator = BookOrchestrator(runner=self.runner, ops=self.ops)

    def _setup_mock_crawl(self) -> None:
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

    def _setup_mock_translate(self) -> None:
        orig_promote = self.ops.promote_translation

        def tracking_promote(*args: Any, **kwargs: Any) -> Any:
            if "translate" not in self.called_phases:
                self.called_phases.append("translate")
            return orig_promote(*args, **kwargs)

        self.ops.promote_translation = tracking_promote

    def run(
        self,
        start_at: str,
        stop_after: str,
        *,
        formats: list[str] | None = None,
        auto_approve: bool = True,
    ) -> RunOutcome:
        self.called_phases = []

        orig_qa = graph_module.run_qa_check
        orig_export = graph_module.export_book

        def tracking_qa(workspace_root: Path, **kwargs: Any) -> Any:
            if "qa" not in self.called_phases:
                self.called_phases.append("qa")
            paths = workspace_paths(workspace_root.parent, workspace_root.name)
            paths.reports.mkdir(parents=True, exist_ok=True)
            from dich_truyen_agent.models import QAReport

            report = QAReport(
                summary={
                    "error_count": 0,
                    "warning_count": 0,
                    "findings_count": 0,
                    "passed": True,
                },
                findings=[],
            )
            atomic_write_yaml(paths.reports / "qa-report.yaml", report)
            return report

        def tracking_export(workspace_root: Path, **kwargs: Any) -> Any:
            if "export" not in self.called_phases:
                self.called_phases.append("export")
            paths = workspace_paths(workspace_root.parent, workspace_root.name)
            paths.exports.mkdir(parents=True, exist_ok=True)
            epub_file = paths.exports / f"{paths.root.name}.epub"
            epub_file.write_bytes(b"PK\x03\x04fake epub content")
            return OperationResult(
                status=OperationStatus.OK,
                reason="exported successfully",
                data={"artifacts": [str(epub_file)]},
            )

        graph_module.run_qa_check = tracking_qa
        graph_module.export_book = tracking_export

        try:
            return self.orchestrator.start(
                self.workspace.root,
                start_at=start_at,
                stop_after=stop_after,
                formats=formats or ["epub"],
                auto_approve=auto_approve,
            )
        finally:
            graph_module.run_qa_check = orig_qa
            graph_module.export_book = orig_export


@pytest.mark.parametrize(
    "start,stop",
    [
        ("crawl", "crawl"),
        ("crawl", "translate"),
        ("crawl", "qa"),
        ("crawl", "export"),
        ("translate", "translate"),
        ("translate", "qa"),
        ("translate", "export"),
        ("qa", "qa"),
        ("qa", "export"),
        ("export", "export"),
    ],
)
def test_valid_spans_enter_only_selected_phases(
    tmp_path: Path, start: str, stop: str
) -> None:
    """All 10 valid explicit phase spans execute and restrict execution strictly within the span."""
    if start == "crawl":
        wf = build_initialized_workspace(tmp_path / f"ws_{start}_{stop}")
    elif start == "translate":
        wf = build_crawl_approved_workspace(tmp_path / f"ws_{start}_{stop}")
    elif start == "qa":
        wf = build_translated_workspace(tmp_path / f"ws_{start}_{stop}")
    else:
        wf = build_qa_approved_workspace(tmp_path / f"ws_{start}_{stop}")

    fixture = EntryTestOrchestrator(wf)
    outcome = fixture.run(start_at=start, stop_after=stop, auto_approve=True)

    assert outcome.status == "completed", f"Failed with: {outcome.error_message}"
    assert outcome.exit_code == 0
    assert outcome.selected_span == (start, stop)

    order = ("crawl", "translate", "qa", "export")
    assert all(
        order.index(start) <= order.index(phase) <= order.index(stop)
        for phase in fixture.called_phases
    )


@pytest.mark.parametrize(
    "start,stop",
    [
        ("translate", "crawl"),
        ("qa", "crawl"),
        ("qa", "translate"),
        ("export", "crawl"),
        ("export", "translate"),
        ("export", "qa"),
    ],
)
def test_invalid_reversed_spans_rejected(tmp_path: Path, start: str, stop: str) -> None:
    """All 6 reversed phase spans are rejected before creating child processes or runs."""
    wf = build_initialized_workspace(tmp_path / f"ws_rev_{start}_{stop}")
    fixture = EntryTestOrchestrator(wf)
    outcome = fixture.run(start_at=start, stop_after=stop)

    assert outcome.status == "blocked"
    assert outcome.exit_code == 3
    assert "cannot precede" in (outcome.error_message or "")
    assert len(fixture.called_phases) == 0


@pytest.mark.parametrize(
    "stop_after",
    ["crawl", "translate", "qa", "export"],
)
def test_auto_endpoints_resolve(tmp_path: Path, stop_after: str) -> None:
    """Auto start resolves the entry phase from current evidence and stops at stop_after."""
    wf = build_initialized_workspace(tmp_path / f"ws_auto_{stop_after}")
    fixture = EntryTestOrchestrator(wf)
    outcome = fixture.run(start_at="auto", stop_after=stop_after, auto_approve=True)

    assert outcome.status == "completed", f"Failed with: {outcome.error_message}"
    assert outcome.exit_code == 0
    assert outcome.selected_span == ("auto", stop_after)
    order = ("crawl", "translate", "qa", "export")
    assert all(order.index(p) <= order.index(stop_after) for p in fixture.called_phases)


def test_e01_auto_start_to_export(tmp_path: Path) -> None:
    """E01: New empty catalog; start_at=auto, stop_after=export runs full lifecycle."""
    wf = build_initialized_workspace(tmp_path / "e01")
    fixture = EntryTestOrchestrator(wf)
    outcome = fixture.run(start_at="auto", stop_after="export", auto_approve=True)

    assert outcome.status == "completed"
    assert outcome.exit_code == 0
    assert "crawl" in fixture.called_phases
    assert "translate" in fixture.called_phases
    assert "qa" in fixture.called_phases
    assert "export" in fixture.called_phases


def test_e02_crawl_crawl(tmp_path: Path) -> None:
    """E02: New catalog; crawl/crawl crawls, approves, and stops without later calls."""
    wf = build_initialized_workspace(tmp_path / "e02")
    fixture = EntryTestOrchestrator(wf)
    outcome = fixture.run(start_at="crawl", stop_after="crawl", auto_approve=True)

    assert outcome.status == "completed"
    assert outcome.exit_code == 0
    assert fixture.called_phases == ["crawl"]


def test_e03_crawl_noop_when_approved(tmp_path: Path) -> None:
    """E03: Complete current crawl gate; crawl/crawl completes as a no-op."""
    wf = build_crawl_approved_workspace(tmp_path / "e03")
    fixture = EntryTestOrchestrator(wf)
    outcome = fixture.run(start_at="crawl", stop_after="crawl")

    assert outcome.status == "completed"
    assert outcome.exit_code == 0
    assert len(fixture.called_phases) == 0


def test_e04_crawl_missing_raw_chapters(tmp_path: Path) -> None:
    """E04: Nonempty catalog with missing raw file; crawl/crawl downloads remaining work."""
    wf = build_initialized_workspace(tmp_path / "e04")
    wf.raw_paths[0].write_text("Raw chapter 1 content\n" * 10, encoding="utf-8")
    fixture = EntryTestOrchestrator(wf)
    outcome = fixture.run(start_at="crawl", stop_after="crawl", auto_approve=True)

    assert outcome.status == "completed"
    assert outcome.exit_code == 0
    assert wf.raw_paths[1].is_file()


def test_e05_translate_direct_entry(tmp_path: Path) -> None:
    """E05: Current crawl gate, partial translations; translate/translate finishes translations."""
    wf = build_crawl_approved_workspace(tmp_path / "e05")
    wf.promote_first_translation()

    fixture = EntryTestOrchestrator(wf)
    outcome = fixture.run(start_at="translate", stop_after="translate")

    assert outcome.status == "completed"
    assert outcome.exit_code == 0
    assert fixture.called_phases == ["translate"]
    assert "crawl" not in fixture.called_phases
    assert "qa" not in fixture.called_phases


def test_e06_translate_blocks_without_crawl_evidence(tmp_path: Path) -> None:
    """E06: Missing or stale crawl gate; translate/translate blocks immediately."""
    wf = build_initialized_workspace(tmp_path / "e06")
    fixture = EntryTestOrchestrator(wf)
    outcome = fixture.run(start_at="translate", stop_after="translate")

    assert outcome.status == "blocked"
    assert outcome.exit_code == 3
    assert "crawl gate is not approved" in (outcome.error_message or "")
    assert len(fixture.called_phases) == 0


def test_e07_translate_noop_when_complete(tmp_path: Path) -> None:
    """E07: All translations valid; translate/translate completes without translator invocation."""
    wf = build_translated_workspace(tmp_path / "e07")
    fixture = EntryTestOrchestrator(wf)
    outcome = fixture.run(start_at="translate", stop_after="translate")

    assert outcome.status == "completed"
    assert outcome.exit_code == 0
    assert len(fixture.called_phases) == 0


def test_e08_qa_direct_entry(tmp_path: Path) -> None:
    """E08: Valid crawl and all translations, no QA gate; qa/qa runs QA and approves."""
    wf = build_translated_workspace(tmp_path / "e08")
    fixture = EntryTestOrchestrator(wf)
    outcome = fixture.run(start_at="qa", stop_after="qa", auto_approve=True)

    assert outcome.status == "completed"
    assert outcome.exit_code == 0
    assert fixture.called_phases == ["qa"]


def test_e09_qa_noop_when_approved(tmp_path: Path) -> None:
    """E09: Current QA gate; qa/qa completes without regenerating report or approval."""
    wf = build_qa_approved_workspace(tmp_path / "e09")
    fixture = EntryTestOrchestrator(wf)
    outcome = fixture.run(start_at="qa", stop_after="qa")

    assert outcome.status == "completed"
    assert outcome.exit_code == 0
    assert len(fixture.called_phases) == 0


def test_e10_qa_blocks_on_gap_or_stale_evidence(tmp_path: Path) -> None:
    """E10: Translation gap (chapter 1 missing translation); qa/qa blocks before QA."""
    wf = build_crawl_approved_workspace(tmp_path / "e10")
    # Only translate chapter 2, leaving chapter 1 missing -> gap!
    trans2 = wf.translation_paths[1]
    trans2.write_text("# Chương 2\n\nNội dung chương 2.\n", encoding="utf-8")
    state = wf.reload_state()
    state.chapters[1].translation = StageRecord(
        status=StageStatus.COMPLETED,
        canonical_path=f"translations/{trans2.name}",
        sha256=sha256_file(trans2),
    )
    atomic_write_yaml(wf.state, state)

    fixture = EntryTestOrchestrator(wf)
    outcome = fixture.run(start_at="qa", stop_after="qa")

    assert outcome.status == "blocked"
    assert outcome.exit_code == 3
    assert len(fixture.called_phases) == 0


def test_e11_export_direct_entry(tmp_path: Path) -> None:
    """E11: Current crawl and QA gates; export/export regenerates requested formats."""
    wf = build_qa_approved_workspace(tmp_path / "e11")
    fixture = EntryTestOrchestrator(wf)
    outcome = fixture.run(start_at="export", stop_after="export")

    assert outcome.status == "completed"
    assert outcome.exit_code == 0
    assert fixture.called_phases == ["export"]


def test_e12_export_blocks_on_missing_qa(tmp_path: Path) -> None:
    """E12: Missing QA gate; export/export blocks without running export."""
    wf = build_translated_workspace(tmp_path / "e12")
    fixture = EntryTestOrchestrator(wf)
    outcome = fixture.run(start_at="export", stop_after="export")

    assert outcome.status == "blocked"
    assert outcome.exit_code == 3
    assert "qa gate is not approved" in (outcome.error_message or "")
    assert len(fixture.called_phases) == 0


def test_e13_auto_satisfied_endpoint_completes(tmp_path: Path) -> None:
    """E13: auto with satisfied endpoint completes without running later phases."""
    wf = build_qa_approved_workspace(tmp_path / "e13")
    fixture = EntryTestOrchestrator(wf)
    outcome = fixture.run(start_at="auto", stop_after="qa")

    assert outcome.status == "completed"
    assert outcome.exit_code == 0
    assert len(fixture.called_phases) == 0


def test_e14_explicit_completed_phase_skips_to_later(tmp_path: Path) -> None:
    """E14: Crawl completed; crawl/qa skips crawl and executes translate and qa."""
    wf = build_crawl_approved_workspace(tmp_path / "e14")
    fixture = EntryTestOrchestrator(wf)
    outcome = fixture.run(start_at="crawl", stop_after="qa", auto_approve=True)

    assert outcome.status == "completed"
    assert outcome.exit_code == 0
    assert "crawl" not in fixture.called_phases
    assert "translate" in fixture.called_phases
    assert "qa" in fixture.called_phases


def test_e15_invalid_phase_parameters_rejected(tmp_path: Path) -> None:
    """E15: Unknown phase name, invalid span, or nonexistent workspace rejected."""
    wf = build_initialized_workspace(tmp_path / "e15")
    fixture = EntryTestOrchestrator(wf)

    res1 = fixture.run(start_at="unknown_phase", stop_after="export")
    assert res1.status == "blocked"
    assert res1.exit_code == 3

    res2 = fixture.run(start_at="crawl", stop_after="invalid_stop")
    assert res2.status == "blocked"
    assert res2.exit_code == 3
