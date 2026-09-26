from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any
from unittest.mock import MagicMock, patch

from dich_truyen_agent.checkpoints import check_gate
from dich_truyen_agent.models import (
    ApprovalScope,
    BookMetadata,
    BookState,
    ChapterCatalog,
    ChapterCatalogEntry,
    ChapterState,
    CheckpointType,
    CrawlReport,
    DiscoveredChapter,
    OperationResult,
    OperationStatus,
    QAFinding,
    QAFindingType,
    QAReport,
    TranslationStyle,
)
from dich_truyen_agent.orchestrator.models import OrchestratorConfig
from dich_truyen_agent.orchestrator.orchestrator import BookOrchestrator
from dich_truyen_agent.orchestrator.runners.mock import MockRunner
from dich_truyen_agent.orchestrator.workspace_ops import WorkspaceOps
from dich_truyen_agent.paths import workspace_paths
from dich_truyen_agent.scope import build_source_scope, save_source_scope
from dich_truyen_agent.storage import atomic_write_yaml, load_yaml_model
from dich_truyen_agent.workspace import initialize_workspace


def _setup_three_chapter_crawl(ws_root: Path) -> None:
    paths = workspace_paths(ws_root.parent, ws_root.name)
    discovered = [
        DiscoveredChapter(
            position=i,
            source_id=f"c{i}",
            source_url=f"https://example.com/c{i}.html",
            original_title=f"第{i}章 Tiêu đề {i}",
            parsed_ordinal=i,
        )
        for i in range(1, 6)
    ]
    scope_rec = build_source_scope(
        discovered, "https://example.com/novel/index.html", limit=3
    )
    save_source_scope(paths.source_scope, scope_rec)

    chapters = [
        ChapterCatalogEntry(
            chapter_id=i,
            slug=f"chuong-{i:04d}",
            source_url=f"https://example.com/c{i}.html",
            original_title=f"第{i}章 Tiêu đề {i}",
            raw_filename=f"{i:04d}-chuong-{i:04d}.txt",
            translation_filename=f"{i:04d}-chuong-{i:04d}.txt",
        )
        for i in range(1, 4)
    ]
    catalog = ChapterCatalog(chapters=chapters)
    atomic_write_yaml(paths.chapters, catalog)

    state = BookState(chapters=[ChapterState(chapter_id=i) for i in range(1, 4)])
    atomic_write_yaml(paths.state, state)

    paths.raw.mkdir(parents=True, exist_ok=True)
    for i in range(1, 4):
        (paths.raw / f"{i:04d}-chuong-{i:04d}.txt").write_text(
            f"第{i}章 Tiêu đề {i}\n\nNội dung chương {i} tiếng Trung..."
            + ("Thêm văn bản nguồn để đủ độ dài... " * 8),
            encoding="utf-8",
        )

    rep = CrawlReport(
        discovered_count=3,
        selected_count=3,
        completed_count=3,
        failed_count=0,
        max_chapters=0,
        scope=ApprovalScope.FULL,
        active_profile_source="shared",
        source_discovered_count=5,
        scope_summary="prefix 3 of 5",
        warnings=[],
    )
    atomic_write_yaml(paths.crawl_report, rep)


def test_end_to_end_three_chapter_scoped_orchestration(tmp_path: Path) -> None:
    books_root = tmp_path / "books"
    slug = "e2e-scoped-novel"
    ws_root = books_root / slug

    ops = WorkspaceOps()

    def fake_crawl(*args: Any, **kwargs: Any) -> OperationResult:
        _setup_three_chapter_crawl(ws_root)
        return OperationResult(status=OperationStatus.OK, reason="crawl succeeded")

    ops.run_crawl = MagicMock(side_effect=fake_crawl)

    translated_order: list[int] = []

    def mock_runner_side_effect(
        workspace: Path, prompt: str, context: dict[str, Any]
    ) -> None:
        phase = context.get("phase")
        if phase == "metadata_translation":
            meta_path = workspace / "book.yaml"
            meta = load_yaml_model(meta_path, BookMetadata)
            meta.translated_title = "Thiên Đạo Đồ Dịch"
            meta.translated_author = "Tác Giả Dịch"
            atomic_write_yaml(meta_path, meta)
        elif phase == "chapter_translation":
            m_cid = re.search(r"chapter_id:\s*(\d+)", prompt)
            assert m_cid is not None
            cid = int(m_cid.group(1))
            translated_order.append(cid)

            m_staged = re.search(r"staged_txt:\s*([^\r\n]+)", prompt)
            assert m_staged is not None
            staged_txt_path = Path(m_staged.group(1).strip())
            staged_txt_path.parent.mkdir(parents=True, exist_ok=True)
            # Write clean valid translation satisfying line 1 prefix, blank line 2, and length ratio
            content = (
                f"# Chương {cid}: Tiêu đề dịch chương {cid}\n\n"
                f"Đoạn văn dịch của chương {cid} rất đầy đủ và chi tiết. "
                "Đây là câu chuyện về hành trình tu tiên đầy gian nan và kỳ thú. "
                "Từng bước vượt qua thử thách để đạt tới cảnh giới tối cao.\n"
            )
            staged_txt_path.write_text(content, encoding="utf-8")

    runner = MockRunner(side_effects=[mock_runner_side_effect])
    orchestrator = BookOrchestrator(runner=runner, ops=ops)
    orchestrator._discover_title = MagicMock(return_value="Thiên Đạo Đồ")

    config = OrchestratorConfig(
        workspace_root=ws_root,
        source_url="https://example.com/novel/index.html",
        book_slug=slug,
        style="tien_hiep",
        scope_limit=3,
        start_at="auto",
        stop_after="export",
        formats=["epub", "pdf"],
        auto_approve=True,
    )

    def fake_calibre(epub_path: Path, output_format: str) -> OperationResult:
        dest = epub_path.with_suffix(f".{output_format}")
        dest.write_bytes(b"%PDF-1.4 mock pdf content")
        return OperationResult(
            status=OperationStatus.OK,
            reason="pdf created",
            report_paths=[str(dest)],
        )

    with (
        patch(
            "dich_truyen_agent.export.run_epubcheck",
            return_value=OperationResult(status=OperationStatus.OK, reason="ok"),
        ),
        patch("dich_truyen_agent.export.run_calibre_convert", side_effect=fake_calibre),
    ):
        outcome = orchestrator.start(config)

    assert outcome.status == "completed"
    assert outcome.exit_code == 0
    assert outcome.current_phase == "export"

    # Verify sequential translation 1 -> 2 -> 3
    assert translated_order == [1, 2, 3]

    # Verify gates
    crawl_gate = check_gate(ws_root, CheckpointType.CRAWL_APPROVED)
    assert crawl_gate.status is OperationStatus.OK

    qa_gate = check_gate(ws_root, CheckpointType.QA_APPROVED)
    assert qa_gate.status is OperationStatus.OK

    # Verify export files exist and > 0 bytes
    paths = workspace_paths(ws_root.parent, ws_root.name)
    epub_file = paths.exports / f"{slug}.epub"
    pdf_file = paths.exports / f"{slug}.pdf"
    assert epub_file.is_file() and epub_file.stat().st_size > 0
    assert pdf_file.is_file() and pdf_file.stat().st_size > 0

    # Verify run summary includes prefix scope
    run_dir = paths.reports / "runs" / outcome.run_id
    summary_path = run_dir / "run_summary.json"
    assert summary_path.is_file()
    summary_data = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary_data["scope_summary"] == "prefix 3 of 5"
    assert summary_data["source_scope_digest"] is not None


def test_legacy_full_book_regression(tmp_path: Path) -> None:
    ws_root = tmp_path / "legacy-book"
    paths = workspace_paths(ws_root.parent, ws_root.name)

    metadata = BookMetadata(
        book_slug="legacy-book",
        title="Legacy Title",
        source_url="https://example.com/legacy/index.html",
        scope_managed=False,
    )
    style = TranslationStyle(name="general", description="General style", tone="casual")
    catalog = ChapterCatalog(
        chapters=[
            ChapterCatalogEntry(
                chapter_id=1,
                slug="chuong-0001",
                source_url="https://example.com/c1.html",
                original_title="第1章 Title 1",
                raw_filename="0001-chuong-0001.txt",
                translation_filename="0001-chuong-0001.txt",
            )
        ]
    )
    initialize_workspace(tmp_path, metadata, catalog, style)

    # Legacy workspace has no reports/source-scope.yaml
    assert not paths.source_scope.is_file()

    # Create raw and crawl report
    (paths.raw / "0001-chuong-0001.txt").write_text("Raw chapter 1", encoding="utf-8")
    rep = CrawlReport(
        discovered_count=1,
        selected_count=1,
        completed_count=1,
        failed_count=0,
        max_chapters=0,
        scope=ApprovalScope.FULL,
        active_profile_source="shared",
        warnings=[],
    )
    atomic_write_yaml(paths.crawl_report, rep)

    # Approve crawl without scope
    from dich_truyen_agent.checkpoints import approve_full_crawl

    app_res = approve_full_crawl(ws_root, rep)
    assert app_res.status is OperationStatus.OK

    # Gate check passes without scope requirement
    gate_res = check_gate(ws_root, CheckpointType.CRAWL_APPROVED)
    assert gate_res.status is OperationStatus.OK


def test_evidence_hash_changed_on_pause_blocks_approval(tmp_path: Path) -> None:
    books_root = tmp_path / "books"
    slug = "pause-tamper-novel"
    ws_root = books_root / slug

    ops = WorkspaceOps()

    def fake_crawl(*args: Any, **kwargs: Any) -> OperationResult:
        _setup_three_chapter_crawl(ws_root)
        return OperationResult(status=OperationStatus.OK, reason="crawl succeeded")

    ops.run_crawl = MagicMock(side_effect=fake_crawl)

    orchestrator = BookOrchestrator(runner=MockRunner(), ops=ops)
    orchestrator._discover_title = MagicMock(return_value="Tamper Test")

    # Start with auto_approve=False so it pauses at crawl approval
    config = OrchestratorConfig(
        workspace_root=ws_root,
        source_url="https://example.com/novel/index.html",
        book_slug=slug,
        style="tien_hiep",
        scope_limit=3,
        start_at="crawl",
        stop_after="crawl",
        auto_approve=False,
    )

    first_run = orchestrator.start(config)
    assert first_run.status == "paused"
    assert first_run.exit_code == 2

    # Tamper with scope evidence during pause
    paths = workspace_paths(ws_root.parent, ws_root.name)
    assert paths.source_scope.is_file()
    tampered = paths.source_scope.read_text(encoding="utf-8") + "\n# Tampered"
    paths.source_scope.write_text(tampered, encoding="utf-8")

    # Resume with approval
    resumed = orchestrator.resume(ws_root, decision="approve")
    assert resumed.status == "blocked"
    assert resumed.exit_code == 3
    assert (
        "evidence changed" in resumed.error_message
        or "verification failed" in resumed.error_message
    )


def test_injected_crawl_failure_blocks_without_approval_prompt(
    tmp_path: Path,
) -> None:
    books_root = tmp_path / "books"
    slug = "crawl-fail-novel"
    ws_root = books_root / slug

    ops = WorkspaceOps()
    # Inject crawl failure
    ops.run_crawl = MagicMock(
        return_value=OperationResult(
            status=OperationStatus.ERROR, reason="Injected crawl network timeout"
        )
    )

    orchestrator = BookOrchestrator(runner=MockRunner(), ops=ops)
    orchestrator._discover_title = MagicMock(return_value="Fail Test")

    config = OrchestratorConfig(
        workspace_root=ws_root,
        source_url="https://example.com/novel/index.html",
        book_slug=slug,
        style="tien_hiep",
        scope_limit=3,
        start_at="auto",
        stop_after="export",
        auto_approve=False,
    )

    outcome = orchestrator.start(config)
    assert outcome.status == "blocked"
    assert outcome.exit_code == 3
    assert outcome.pending_approval is None
    assert "Injected crawl network timeout" in outcome.error_message


def test_injected_qa_error_blocks_without_approval_prompt(tmp_path: Path) -> None:
    books_root = tmp_path / "books"
    slug = "qa-fail-novel"
    ws_root = books_root / slug

    ops = WorkspaceOps()

    def fake_crawl(*args: Any, **kwargs: Any) -> OperationResult:
        _setup_three_chapter_crawl(ws_root)
        return OperationResult(status=OperationStatus.OK, reason="crawl succeeded")

    ops.run_crawl = MagicMock(side_effect=fake_crawl)

    def mock_runner_side_effect(
        workspace: Path, prompt: str, context: dict[str, Any]
    ) -> None:
        phase = context.get("phase")
        if phase == "metadata_translation":
            meta_path = workspace / "book.yaml"
            meta = load_yaml_model(meta_path, BookMetadata)
            meta.translated_title = "Thiên Đạo Đồ Dịch"
            atomic_write_yaml(meta_path, meta)
        elif phase == "chapter_translation":
            m_cid = re.search(r"chapter_id:\s*(\d+)", prompt)
            assert m_cid is not None
            cid = int(m_cid.group(1))

            m_staged = re.search(r"staged_txt:\s*([^\r\n]+)", prompt)
            assert m_staged is not None
            staged_txt_path = Path(m_staged.group(1).strip())
            staged_txt_path.parent.mkdir(parents=True, exist_ok=True)
            content = (
                f"# Chương {cid}: Tiêu đề dịch chương {cid}\n\n"
                f"Đoạn văn dịch của chương {cid} rất đầy đủ và chi tiết.\n"
            )
            staged_txt_path.write_text(content, encoding="utf-8")

    runner = MockRunner(side_effects=[mock_runner_side_effect])
    orchestrator = BookOrchestrator(runner=runner, ops=ops)
    orchestrator._discover_title = MagicMock(return_value="Thiên Đạo Đồ")

    # Injected QA error via patching run_qa_check
    injected_qa_report = QAReport(
        summary={"error_count": 1, "warning_count": 0, "findings_count": 1},
        findings=[
            QAFinding(
                chapter_id=1,
                finding_type=QAFindingType.STRUCTURAL,
                severity="error",
                message="Critical injected QA error: translation corrupted",
            )
        ],
    )

    config = OrchestratorConfig(
        workspace_root=ws_root,
        source_url="https://example.com/novel/index.html",
        book_slug=slug,
        style="tien_hiep",
        scope_limit=3,
        start_at="auto",
        stop_after="export",
        auto_approve=True,
    )

    with patch(
        "dich_truyen_agent.orchestrator.graph.run_qa_check",
        return_value=injected_qa_report,
    ):
        outcome = orchestrator.start(config)

    assert outcome.status == "blocked"
    assert outcome.exit_code == 3
    assert outcome.pending_approval is None
    assert outcome.error_code == "needs_repair"
    assert "QA check found 1 critical errors" in outcome.error_message


def test_missing_requested_pdf_blocks_completion(tmp_path: Path) -> None:
    books_root = tmp_path / "books"
    slug = "missing-pdf-novel"
    ws_root = books_root / slug

    ops = WorkspaceOps()

    def fake_crawl(*args: Any, **kwargs: Any) -> OperationResult:
        _setup_three_chapter_crawl(ws_root)
        return OperationResult(status=OperationStatus.OK, reason="crawl succeeded")

    ops.run_crawl = MagicMock(side_effect=fake_crawl)

    def mock_runner_side_effect(
        workspace: Path, prompt: str, context: dict[str, Any]
    ) -> None:
        phase = context.get("phase")
        if phase == "metadata_translation":
            meta_path = workspace / "book.yaml"
            meta = load_yaml_model(meta_path, BookMetadata)
            meta.translated_title = "Thiên Đạo Đồ Dịch"
            atomic_write_yaml(meta_path, meta)
        elif phase == "chapter_translation":
            m_cid = re.search(r"chapter_id:\s*(\d+)", prompt)
            assert m_cid is not None
            cid = int(m_cid.group(1))

            m_staged = re.search(r"staged_txt:\s*([^\r\n]+)", prompt)
            assert m_staged is not None
            staged_txt_path = Path(m_staged.group(1).strip())
            staged_txt_path.parent.mkdir(parents=True, exist_ok=True)
            content = (
                f"# Chương {cid}: Tiêu đề dịch chương {cid}\n\n"
                f"Đoạn văn dịch của chương {cid} rất đầy đủ và chi tiết. "
                "Đây là câu chuyện về hành trình tu tiên đầy gian nan và kỳ thú. "
                "Từng bước vượt qua thử thách để đạt tới cảnh giới tối cao.\n"
            )
            staged_txt_path.write_text(content, encoding="utf-8")

    runner = MockRunner(side_effects=[mock_runner_side_effect])
    orchestrator = BookOrchestrator(runner=runner, ops=ops)
    orchestrator._discover_title = MagicMock(return_value="Thiên Đạo Đồ")

    config = OrchestratorConfig(
        workspace_root=ws_root,
        source_url="https://example.com/novel/index.html",
        book_slug=slug,
        style="tien_hiep",
        scope_limit=3,
        start_at="auto",
        stop_after="export",
        formats=["epub", "pdf"],
        auto_approve=True,
    )

    # Calibre conversion returns OK, but does NOT write the destination file
    def calibre_noop(epub_path: Path, output_format: str) -> OperationResult:
        dest = epub_path.with_suffix(f".{output_format}")
        # Note: file is NOT written!
        return OperationResult(
            status=OperationStatus.OK,
            reason="pretended pdf created",
            report_paths=[str(dest)],
        )

    with (
        patch(
            "dich_truyen_agent.export.run_epubcheck",
            return_value=OperationResult(status=OperationStatus.OK, reason="ok"),
        ),
        patch("dich_truyen_agent.export.run_calibre_convert", side_effect=calibre_noop),
    ):
        outcome = orchestrator.start(config)

    assert outcome.status == "blocked"
    assert outcome.exit_code == 3
    assert "pdf" in outcome.error_message
