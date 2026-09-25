from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from dich_truyen_agent.checkpoints import approve_full_crawl
from dich_truyen_agent.cli import build_parser, run_command
from dich_truyen_agent.crawl_batch import crawl_book
from dich_truyen_agent.models import (
    BookMetadata,
    BookState,
    ChapterCatalog,
    ChapterCatalogEntry,
    ChapterState,
    CrawlReport,
    CrawlSettings,
    OperationResult,
    OperationStatus,
    StageRecord,
    StageStatus,
    TranslationStyle,
)
from dich_truyen_agent.paths import workspace_paths
from dich_truyen_agent.storage import atomic_write_yaml, load_yaml_model, sha256_file
from dich_truyen_agent.workspace import initialize_workspace


class MockStaticCrawler:
    def __init__(self, settings: CrawlSettings, *, zero_chapters: bool = False):
        self.settings = settings
        self.zero_chapters = zero_chapters
        self.fetch_calls: list[str] = []

    async def close(self) -> None:
        pass

    async def fetch(self, url: str) -> tuple[bytes, str | None]:
        self.fetch_calls.append(url)
        if "index" in url:
            if self.zero_chapters:
                html = "<html><body><div class='centent'><ul></ul></div></body></html>"
            else:
                html = """
                <html>
                  <head><title>Test Book - 飘天文学</title></head>
                  <body>
                    <div class="centent">
                      <ul>
                        <li><a href="c1.html">第一章 Chapter One</a></li>
                        <li><a href="c2.html">第二章 Chapter Two</a></li>
                        <li><a href="c3.html">第三章 Chapter Three</a></li>
                      </ul>
                    </div>
                  </body>
                </html>
                """
            return html.encode("gbk"), "gbk"
        elif "c1" in url:
            html = "<h1>Chapter One</h1><div id='content'>Content of chapter 1. Text is long enough to satisfy minimum characters rule easily.</div>"
            return html.encode("gbk"), "gbk"
        elif "c2" in url:
            html = "<h1>Chapter Two</h1><div id='content'>Content of chapter 2. Text is long enough to satisfy minimum characters rule easily.</div>"
            return html.encode("gbk"), "gbk"
        elif "c3" in url:
            html = "<h1>Chapter Three</h1><div id='content'>Content of chapter 3. Text is long enough to satisfy minimum characters rule easily.</div>"
            return html.encode("gbk"), "gbk"
        raise ValueError(f"unexpected url: {url}")


@pytest.fixture
def mock_project(tmp_path: Path) -> Path:
    project_root = tmp_path / "project"
    project_root.mkdir()
    profile_dir = project_root / "templates" / "crawl_profiles"
    profile_dir.mkdir(parents=True)
    style_dir = project_root / "templates" / "styles"
    style_dir.mkdir(parents=True)

    profile_content = """
schema_version: 1
domain: www.piaotia.com
index:
  chapter_link_selector: ".centent ul li a"
  pagination_selector: null
  list_section_selectors: []
chapter:
  title_selector: "h1"
  content_selector: "#content"
  remove_selectors: ["script"]
encoding:
  index: "gbk"
  chapter: "gbk"
validation:
  min_chapter_characters: 20
"""
    (profile_dir / "www.piaotia.com.yaml").write_text(profile_content, encoding="utf-8")

    general_style = """
name: "general"
description: "General template"
guidelines: []
vocabulary: {}
tone: "natural"
examples: []
"""
    (style_dir / "general.yaml").write_text(general_style, encoding="utf-8")
    return project_root


@pytest.mark.asyncio
async def test_empty_catalog_enters_discovery(tmp_path: Path, mock_project: Path) -> None:
    books_root = tmp_path / "books"
    slug = "empty-catalog-book"
    source_url = "https://www.piaotia.com/html/1/123/index.html"

    # Initialize workspace with empty catalog
    metadata = BookMetadata(
        book_slug=slug,
        source_url=source_url,
        title="Empty Catalog Book",
        author="Author",
    )
    catalog = ChapterCatalog(chapters=[])
    style = TranslationStyle(name="general", description="desc", tone="tone")
    initialize_workspace(books_root, metadata, catalog, style)

    crawler = MockStaticCrawler(CrawlSettings())
    result = await crawl_book(
        books_root=books_root,
        book_slug=slug,
        source_url=source_url,
        project_root=mock_project,
        static_crawler_class=lambda s: crawler,
    )

    assert result.status is OperationStatus.OK
    # Index URL must have been fetched
    assert source_url in crawler.fetch_calls
    # Catalog is updated with discovered chapters
    paths = workspace_paths(books_root, slug)
    updated_catalog = load_yaml_model(paths.chapters, ChapterCatalog)
    assert len(updated_catalog.chapters) == 3
    assert (paths.raw / "0001-chapter-one.txt").is_file()
    assert (paths.raw / "0002-chapter-two.txt").is_file()
    assert (paths.raw / "0003-chapter-three.txt").is_file()


@pytest.mark.asyncio
async def test_nonempty_catalog_skips_discovery_and_downloads_only_missing(
    tmp_path: Path, mock_project: Path
) -> None:
    books_root = tmp_path / "books"
    slug = "existing-catalog-book"
    source_url = "https://www.piaotia.com/html/1/123/index.html"

    paths = workspace_paths(books_root, slug)
    metadata = BookMetadata(
        book_slug=slug,
        source_url=source_url,
        title="Existing Catalog Book",
        author="Author",
    )
    catalog = ChapterCatalog(
        chapters=[
            ChapterCatalogEntry(
                chapter_id=1,
                slug="0001-ch1",
                source_url="https://www.piaotia.com/html/1/123/c1.html",
                original_title="Ch 1",
                raw_filename="0001-ch1.txt",
                translation_filename="0001-ch1.txt",
            ),
            ChapterCatalogEntry(
                chapter_id=2,
                slug="0002-ch2",
                source_url="https://www.piaotia.com/html/1/123/c2.html",
                original_title="Ch 2",
                raw_filename="0002-ch2.txt",
                translation_filename="0002-ch2.txt",
            ),
            ChapterCatalogEntry(
                chapter_id=3,
                slug="0003-ch3",
                source_url="https://www.piaotia.com/html/1/123/c3.html",
                original_title="Ch 3",
                raw_filename="0003-ch3.txt",
                translation_filename="0003-ch3.txt",
            ),
        ]
    )
    style = TranslationStyle(name="general", description="desc", tone="tone")
    initialize_workspace(books_root, metadata, catalog, style)

    # Pre-populate chapter 1 as completed
    ch1_raw = paths.raw / "0001-ch1.txt"
    ch1_raw.write_text("Chapter 1 existing raw text body", encoding="utf-8")
    ch1_hash = sha256_file(ch1_raw)

    state = BookState(
        chapters=[
            ChapterState(
                chapter_id=1,
                raw=StageRecord(
                    status=StageStatus.COMPLETED,
                    canonical_path="raw/0001-ch1.txt",
                    sha256=ch1_hash,
                ),
            ),
            ChapterState(chapter_id=2),
            ChapterState(chapter_id=3),
        ]
    )
    atomic_write_yaml(paths.state, state)

    crawler = MockStaticCrawler(CrawlSettings())
    result = await crawl_book(
        books_root=books_root,
        book_slug=slug,
        source_url=source_url,
        project_root=mock_project,
        static_crawler_class=lambda s: crawler,
    )

    assert result.status is OperationStatus.OK
    # Discovery must be skipped - index URL is NOT fetched
    assert source_url not in crawler.fetch_calls
    # Only c2 and c3 are fetched
    assert "https://www.piaotia.com/html/1/123/c1.html" not in crawler.fetch_calls
    assert "https://www.piaotia.com/html/1/123/c2.html" in crawler.fetch_calls
    assert "https://www.piaotia.com/html/1/123/c3.html" in crawler.fetch_calls

    assert (paths.raw / "0002-ch2.txt").is_file()
    assert (paths.raw / "0003-ch3.txt").is_file()


@pytest.mark.asyncio
async def test_zero_discovered_chapters_returns_blocked(
    tmp_path: Path, mock_project: Path
) -> None:
    books_root = tmp_path / "books"
    slug = "zero-book"
    source_url = "https://www.piaotia.com/html/1/123/index.html"

    crawler = MockStaticCrawler(CrawlSettings(), zero_chapters=True)
    result = await crawl_book(
        books_root=books_root,
        book_slug=slug,
        source_url=source_url,
        project_root=mock_project,
        static_crawler_class=lambda s: crawler,
    )

    assert result.status is OperationStatus.BLOCKED
    assert "zero chapters" in result.reason

    # Verify that a zero-chapter report cannot be approved
    from dich_truyen_agent.models import ApprovalScope
    dummy_report = CrawlReport(
        discovered_count=0,
        selected_count=0,
        completed_count=0,
        failed_count=0,
        max_chapters=0,
        scope=ApprovalScope.FULL,
        active_profile_source="shared",
    )
    workspace_root = workspace_paths(books_root, slug).root
    approve_res = approve_full_crawl(workspace_root, dummy_report)
    assert approve_res.status is OperationStatus.BLOCKED


def test_crawl_book_json_stdout_and_exit_code(
    tmp_path: Path, mock_project: Path, capsys: pytest.CaptureFixture
) -> None:
    books_root = tmp_path / "books"
    slug = "json-crawl-book"
    source_url = "https://www.piaotia.com/html/1/123/index.html"

    parser = build_parser()
    args = parser.parse_args(
        [
            "crawl-book",
            "--books-root",
            str(books_root),
            "--slug",
            slug,
            "--source-url",
            source_url,
            "--json",
        ]
    )

    with patch("dich_truyen_agent.cli.PROJECT_ROOT", mock_project):
        with patch(
            "dich_truyen_agent.crawl_batch.StaticCrawler",
            lambda s: MockStaticCrawler(s, zero_chapters=True),
        ):
            # run_command returns OperationResult; main prints JSON
            result = run_command(args)
            assert result.status is OperationStatus.BLOCKED

            from dich_truyen_agent.cli import _print_json_result

            _print_json_result(result)
            captured = capsys.readouterr()
            payload = json.loads(captured.out)
            parsed = OperationResult.model_validate(payload)
            assert parsed.status is OperationStatus.BLOCKED
            assert "zero chapters" in parsed.reason


@pytest.mark.asyncio
async def test_max_chapters_and_delay_configuration(
    tmp_path: Path, mock_project: Path
) -> None:
    books_root = tmp_path / "books"
    slug = "config-crawl-book"
    source_url = "https://www.piaotia.com/html/1/123/index.html"

    delays: list[float] = []

    async def mock_sleep(seconds: float) -> None:
        delays.append(seconds)

    # 1. max_chapters = 0 (unlimited scope, downloads all 3 discovered chapters)
    crawler = MockStaticCrawler(CrawlSettings(max_chapters=0, chapter_delay_seconds=4.5))
    result = await crawl_book(
        books_root=books_root,
        book_slug=slug,
        source_url=source_url,
        project_root=mock_project,
        max_chapters=0,
        chapter_delay_seconds=4.5,
        sleeper_fn=mock_sleep,
        static_crawler_class=lambda s: crawler,
    )
    assert result.status is OperationStatus.OK
    assert result.progress is not None
    assert result.progress.total == 3
    assert result.progress.completed == 3
    # 4.5s delay should have been recorded between chapters
    assert 4.5 in delays
