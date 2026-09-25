from __future__ import annotations

from pathlib import Path

import pytest

from dich_truyen_agent.orchestrator.workspace_ops import WorkspaceOps
from orchestrator_support import (
    WorkspaceFixture,
    build_crawl_approved_workspace,
    build_initialized_workspace,
    build_qa_approved_workspace,
    build_translated_workspace,
)


@pytest.fixture
def initialized_workspace(tmp_path: Path) -> WorkspaceFixture:
    return build_initialized_workspace(tmp_path / "init", chapter_count=2)


@pytest.fixture
def crawl_approved_workspace(tmp_path: Path) -> WorkspaceFixture:
    return build_crawl_approved_workspace(tmp_path / "crawl", chapter_count=2)


@pytest.fixture
def translated_workspace(tmp_path: Path) -> WorkspaceFixture:
    return build_translated_workspace(tmp_path / "translated", chapter_count=2)


@pytest.fixture
def qa_approved_workspace(tmp_path: Path) -> WorkspaceFixture:
    return build_qa_approved_workspace(tmp_path / "qa", chapter_count=2)


def test_export_entry_uses_workspace_not_graph_history(qa_approved_workspace: WorkspaceFixture) -> None:
    decision = WorkspaceOps().inspect_entry(qa_approved_workspace.root, "export", "export")
    assert decision.phase == "export"
    assert decision.status == "enter"


@pytest.mark.parametrize(
    "start,stop,expected_status,expected_phase",
    [
        ("crawl", "crawl", "completed", "crawl"),
        ("crawl", "translate", "enter", "translate"),
        ("crawl", "qa", "enter", "translate"),
        ("crawl", "export", "enter", "translate"),
        ("translate", "translate", "enter", "translate"),
        ("translate", "qa", "enter", "translate"),
        ("translate", "export", "enter", "translate"),
    ],
)
def test_valid_explicit_spans_on_crawl_approved(
    crawl_approved_workspace: WorkspaceFixture,
    start: str,
    stop: str,
    expected_status: str,
    expected_phase: str,
) -> None:
    decision = WorkspaceOps().inspect_entry(crawl_approved_workspace.root, start, stop)
    assert decision.status == expected_status
    assert decision.phase == expected_phase


@pytest.mark.parametrize(
    "start,stop,expected_status,expected_phase",
    [
        ("translate", "translate", "completed", "translate"),
        ("translate", "qa", "enter", "qa"),
        ("translate", "export", "enter", "qa"),
        ("qa", "qa", "enter", "qa"),
        ("qa", "export", "enter", "qa"),
    ],
)
def test_valid_explicit_spans_on_translated(
    translated_workspace: WorkspaceFixture,
    start: str,
    stop: str,
    expected_status: str,
    expected_phase: str,
) -> None:
    decision = WorkspaceOps().inspect_entry(translated_workspace.root, start, stop)
    assert decision.status == expected_status
    assert decision.phase == expected_phase


def test_qa_completed_span_is_noop_on_qa_approved(qa_approved_workspace: WorkspaceFixture) -> None:
    decision = WorkspaceOps().inspect_entry(qa_approved_workspace.root, "qa", "qa")
    assert decision.status == "completed"
    assert decision.phase == "qa"


def test_qa_to_export_enters_export_on_qa_approved(qa_approved_workspace: WorkspaceFixture) -> None:
    decision = WorkspaceOps().inspect_entry(qa_approved_workspace.root, "qa", "export")
    assert decision.status == "enter"
    assert decision.phase == "export"


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
def test_reversed_spans_return_blocked(crawl_approved_workspace: WorkspaceFixture, start: str, stop: str) -> None:
    decision = WorkspaceOps().inspect_entry(crawl_approved_workspace.root, start, stop)
    assert decision.status == "blocked"
    assert "cannot precede" in decision.reason


def test_auto_endpoints_find_earliest_incomplete_phase(
    initialized_workspace: WorkspaceFixture,
    crawl_approved_workspace: WorkspaceFixture,
    translated_workspace: WorkspaceFixture,
    qa_approved_workspace: WorkspaceFixture,
) -> None:
    ops = WorkspaceOps()

    # 1. On initialized workspace: crawl is earliest
    d1 = ops.inspect_entry(initialized_workspace.root, "auto", "export")
    assert d1.status == "enter"
    assert d1.phase == "crawl"

    # 2. On crawl-approved workspace: translate is earliest
    d2 = ops.inspect_entry(crawl_approved_workspace.root, "auto", "export")
    assert d2.status == "enter"
    assert d2.phase == "translate"

    # 3. On translated workspace: qa is earliest
    d3 = ops.inspect_entry(translated_workspace.root, "auto", "export")
    assert d3.status == "enter"
    assert d3.phase == "qa"

    # 4. On qa-approved workspace: export is earliest (formats missing)
    d4 = ops.inspect_entry(qa_approved_workspace.root, "auto", "export", formats=["epub", "txt"])
    assert d4.status == "enter"
    assert d4.phase == "export"

    # 5. On qa-approved with existing exports: completed
    export_dir = qa_approved_workspace.root / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    (export_dir / "test-book.epub").write_bytes(b"dummy-epub")
    (export_dir / "test-book.txt").write_bytes(b"dummy-txt")

    d5 = ops.inspect_entry(qa_approved_workspace.root, "auto", "export", formats=["epub", "txt"])
    assert d5.status == "completed"
    assert d5.phase == "export"


def test_explicit_start_blocks_on_missing_prerequisites_without_backtracking(
    initialized_workspace: WorkspaceFixture,
    crawl_approved_workspace: WorkspaceFixture,
) -> None:
    ops = WorkspaceOps()

    # 1. Explicit translate on unapproved crawl: blocks, does NOT enter crawl
    res_trans = ops.inspect_entry(initialized_workspace.root, "translate", "translate")
    assert res_trans.status == "blocked"
    assert res_trans.missing_gate == "crawl-approved"
    assert "remedy_command" in dir(res_trans) and res_trans.remedy_command is not None

    # 2. Explicit qa on incomplete translations: blocks, does NOT enter translate
    res_qa = ops.inspect_entry(crawl_approved_workspace.root, "qa", "qa")
    assert res_qa.status == "blocked"
    assert res_qa.missing_gate == "translation-completed"

    # 3. Explicit export on incomplete QA: blocks, does NOT enter qa
    res_export = ops.inspect_entry(crawl_approved_workspace.root, "export", "export")
    assert res_export.status == "blocked"
    assert "crawl-approved" in (res_export.missing_gate or "") or "translation" in res_export.reason.lower()


def test_empty_catalog_blocks_explicit_translation_entry(tmp_path: Path) -> None:
    wf = build_initialized_workspace(tmp_path, chapter_count=0)
    decision = WorkspaceOps().inspect_entry(wf.root, "translate", "translate")
    assert decision.status == "blocked"
    assert "crawl gate is not approved" in decision.reason or "catalog has zero chapters" in decision.reason
