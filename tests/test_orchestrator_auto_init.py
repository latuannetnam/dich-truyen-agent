from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from dich_truyen_agent.models import BookMetadata, OperationResult, OperationStatus
from dich_truyen_agent.orchestrator.models import OrchestratorConfig
from dich_truyen_agent.orchestrator.orchestrator import BookOrchestrator
from dich_truyen_agent.orchestrator.runners.mock import MockRunner
from dich_truyen_agent.orchestrator.workspace_ops import WorkspaceOps
from dich_truyen_agent.storage import load_yaml_model


def test_auto_init_with_discovered_title(tmp_path: Path) -> None:
    books_root = tmp_path / "books"
    slug = "auto-init-novel"
    ws_root = books_root / slug

    ops = WorkspaceOps()

    def fake_crawl(*args: Any, **kwargs: Any) -> OperationResult:
        from dich_truyen_agent.models import (
            ApprovalScope,
            BookState,
            ChapterCatalog,
            ChapterCatalogEntry,
            ChapterState,
            CrawlReport,
            DiscoveredChapter,
        )
        from dich_truyen_agent.paths import workspace_paths
        from dich_truyen_agent.scope import build_source_scope, save_source_scope
        from dich_truyen_agent.storage import atomic_write_yaml

        paths = workspace_paths(ws_root.parent, ws_root.name)
        discovered = [
            DiscoveredChapter(
                position=i,
                source_id=f"c{i}",
                source_url=f"u{i}",
                original_title=f"t{i}",
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
                slug=f"c{i}",
                source_url=f"u{i}",
                original_title=f"t{i}",
                raw_filename=f"c{i}.txt",
                translation_filename=f"c{i}.md",
            )
            for i in range(1, 4)
        ]
        catalog = ChapterCatalog(chapters=chapters)
        atomic_write_yaml(paths.chapters, catalog)

        state = BookState(chapters=[ChapterState(chapter_id=i) for i in range(1, 4)])
        atomic_write_yaml(paths.state, state)

        for i in range(1, 4):
            (paths.raw / f"c{i}.txt").write_text(f"Raw body {i}\n", encoding="utf-8")

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
        return OperationResult(status=OperationStatus.OK, reason="ok")

    ops.run_crawl = MagicMock(side_effect=fake_crawl)

    orchestrator = BookOrchestrator(runner=MockRunner(), ops=ops)
    orchestrator._discover_title = MagicMock(return_value="Thiên Đạo Đồ")

    config = OrchestratorConfig(
        workspace_root=ws_root,
        source_url="https://example.com/novel/index.html",
        book_slug=slug,
        style="tien_hiep",
        scope_limit=3,
        stop_after="crawl",
        auto_approve=True,
    )

    outcome = orchestrator.start(config)
    assert outcome.status in ("completed", "paused")
    assert ws_root.is_dir()
    assert (ws_root / "book.yaml").is_file()
    assert (ws_root / "chapters.yaml").is_file()
    assert (ws_root / "style.yaml").is_file()

    meta = load_yaml_model(ws_root / "book.yaml", BookMetadata)
    assert meta.title == "Thiên Đạo Đồ"
    assert meta.scope_managed is True
    assert meta.source_url == "https://example.com/novel/index.html"


def test_auto_init_with_supplied_title_when_discovery_fails(tmp_path: Path) -> None:
    books_root = tmp_path / "books"
    slug = "supplied-title-novel"
    ws_root = books_root / slug

    ops = WorkspaceOps()
    # Crawl will be called once empty catalog workspace is initialized
    ops.run_crawl = MagicMock(
        return_value=OperationResult(status=OperationStatus.OK, reason="ok")
    )

    orchestrator = BookOrchestrator(runner=MockRunner(), ops=ops)
    orchestrator._discover_title = MagicMock(return_value=None)

    config = OrchestratorConfig(
        workspace_root=ws_root,
        source_url="https://example.com/novel/index.html",
        book_slug=slug,
        title="Explicit Novel Title",
        style="general",
        scope_limit=5,
        stop_after="crawl",
    )

    _ = orchestrator.start(config)
    assert ws_root.is_dir()
    meta = load_yaml_model(ws_root / "book.yaml", BookMetadata)
    assert meta.title == "Explicit Novel Title"
    assert meta.scope_managed is True


def test_missing_title_with_failed_discovery_leaves_no_initialized_workspace(
    tmp_path: Path,
) -> None:
    books_root = tmp_path / "books"
    slug = "failed-discovery-novel"
    ws_root = books_root / slug

    orchestrator = BookOrchestrator(runner=MockRunner(), ops=WorkspaceOps())
    orchestrator._discover_title = MagicMock(return_value=None)

    config = OrchestratorConfig(
        workspace_root=ws_root,
        source_url="https://example.com/novel/index.html",
        book_slug=slug,
        title=None,
        style="tien_hiep",
    )

    outcome = orchestrator.start(config)
    assert outcome.status == "blocked"
    assert outcome.exit_code == 3
    assert "title" in (outcome.error_message or "").lower()

    # Workspace must not exist
    assert not ws_root.exists()


def test_invalid_style_blocks_before_network(tmp_path: Path) -> None:
    books_root = tmp_path / "books"
    slug = "invalid-style-novel"
    ws_root = books_root / slug

    orchestrator = BookOrchestrator(runner=MockRunner(), ops=WorkspaceOps())
    discover_mock = MagicMock()
    orchestrator._discover_title = discover_mock

    config = OrchestratorConfig(
        workspace_root=ws_root,
        source_url="https://example.com/novel/index.html",
        book_slug=slug,
        title="My Title",
        style="nonexistent_style_xyz",
    )

    outcome = orchestrator.start(config)
    assert outcome.status == "blocked"
    assert outcome.exit_code == 3
    assert not ws_root.exists()
    assert discover_mock.call_count == 0


def test_retry_on_initialized_workspace_rejects_conflicting_limit(
    tmp_path: Path,
) -> None:
    books_root = tmp_path / "books"
    slug = "existing-scoped-novel"
    ws_root = books_root / slug

    # Initialize workspace with scope_limit=3
    ops = WorkspaceOps()
    ops.run_crawl = MagicMock(
        return_value=OperationResult(status=OperationStatus.OK, reason="ok")
    )

    orchestrator = BookOrchestrator(runner=MockRunner(), ops=ops)
    orchestrator._discover_title = MagicMock(return_value="Test Novel")

    config1 = OrchestratorConfig(
        workspace_root=ws_root,
        source_url="https://example.com/novel/index.html",
        book_slug=slug,
        style="general",
        scope_limit=3,
        stop_after="crawl",
        auto_approve=True,
    )
    _ = orchestrator.start(config1)

    # Fake reports/source-scope.yaml with limit=3
    from dich_truyen_agent.scope import build_source_scope, save_source_scope
    from dich_truyen_agent.models import DiscoveredChapter

    discovered = [
        DiscoveredChapter(
            position=i,
            source_id=f"c{i}",
            source_url=f"u{i}",
            original_title=f"t{i}",
            parsed_ordinal=i,
        )
        for i in range(1, 6)
    ]
    scope_rec = build_source_scope(
        discovered, "https://example.com/novel/index.html", limit=3
    )
    save_source_scope(ws_root / "reports" / "source-scope.yaml", scope_rec)

    # Try starting again with scope_limit=5 -> must block
    config2 = OrchestratorConfig(
        workspace_root=ws_root,
        source_url="https://example.com/novel/index.html",
        book_slug=slug,
        style="general",
        scope_limit=5,
        stop_after="crawl",
    )
    outcome2 = orchestrator.start(config2)
    assert outcome2.status == "blocked"
    assert "scope" in (outcome2.error_message or "").lower()
