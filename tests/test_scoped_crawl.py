from __future__ import annotations

from pathlib import Path
import pytest

from dich_truyen_agent.crawl_batch import crawl_book
from dich_truyen_agent.crawl_profiles import load_active_crawl_profile
from dich_truyen_agent.crawl_reports import build_crawl_report
from dich_truyen_agent.models import (
    ApprovalScope,
    BookState,
    ChapterCatalog,
    CrawlSettings,
    OperationStatus,
    SourceScopeRecord,
)
from dich_truyen_agent.paths import workspace_paths
from dich_truyen_agent.scope import load_source_scope
from dich_truyen_agent.storage import load_yaml_model


class FiveChapterCrawler:
    def __init__(self, settings: CrawlSettings):
        self.settings = settings
        self.fetch_calls: list[str] = []
        self.catalog_source = "normal"

    async def fetch(self, url: str) -> tuple[bytes, str | None]:
        self.fetch_calls.append(url)
        if "index" in url:
            if self.catalog_source == "normal":
                html = """
                <html>
                  <head><title>My Novel Title - 飘天文学</title></head>
                  <body>
                    <div class="centent">
                      <ul>
                        <li><a href="c1.html">第一章 Title 1</a></li>
                        <li><a href="c2.html">第二章 Title 2</a></li>
                        <li><a href="c3.html">第三章 Title 3</a></li>
                        <li><a href="c4.html">第四章 Title 4</a></li>
                        <li><a href="c5.html">第五章 Title 5</a></li>
                      </ul>
                    </div>
                  </body>
                </html>
                """
            elif self.catalog_source == "changed":
                html = """
                <html>
                  <head><title>My Novel Title - 飘天文学</title></head>
                  <body>
                    <div class="centent">
                      <ul>
                        <li><a href="c1.html">第一章 Title 1 Modified</a></li>
                        <li><a href="c2.html">第二章 Title 2</a></li>
                        <li><a href="c3.html">第三章 Title 3</a></li>
                        <li><a href="c4.html">第四章 Title 4</a></li>
                        <li><a href="c5.html">第五章 Title 5</a></li>
                      </ul>
                    </div>
                  </body>
                </html>
                """
            elif self.catalog_source == "gap_outside":
                html = """
                <html>
                  <head><title>My Novel Title - 飘天文学</title></head>
                  <body>
                    <div class="centent">
                      <ul>
                        <li><a href="c1.html">第一章 Title 1</a></li>
                        <li><a href="c2.html">第二章 Title 2</a></li>
                        <li><a href="c3.html">第三章 Title 3</a></li>
                        <li><a href="c5.html">第五章 Title 5</a></li>
                        <li><a href="c6.html">第六章 Title 6</a></li>
                      </ul>
                    </div>
                  </body>
                </html>
                """
            elif self.catalog_source == "duplicate_url":
                html = """
                <html>
                  <head><title>My Novel Title - 飘天文学</title></head>
                  <body>
                    <div class="centent">
                      <ul>
                        <li><a href="c1.html">第一章 Title 1</a></li>
                        <li><a href="c1.html">第二章 Title 2</a></li>
                        <li><a href="c3.html">第三章 Title 3</a></li>
                        <li><a href="c4.html">第四章 Title 4</a></li>
                        <li><a href="c5.html">第五章 Title 5</a></li>
                      </ul>
                    </div>
                  </body>
                </html>
                """
            elif self.catalog_source == "empty":
                html = """
                <html>
                  <head><title>My Novel Title - 飘天文学</title></head>
                  <body><div class="centent"><ul></ul></div></body>
                </html>
                """
            return html.encode("gbk"), "gbk"

        for i in range(1, 10):
            if f"c{i}" in url:
                html = (
                    f"<h1>Title {i}</h1><div id='content'>Content of chapter {i}. "
                    + ("Valid content text here... " * 10)
                    + "</div>"
                )
                return html.encode("gbk"), "gbk"

        raise ValueError(f"Unknown URL {url}")

    async def close(self) -> None:
        pass


class DummyRenderer:
    async def render(self, url: str, profile, *, purpose: str = "chapter") -> str:
        return (
            "<h1>JS Title</h1><div id='content'>Content text... "
            + ("Valid content text here... " * 10)
            + "</div>"
        )

    async def close(self) -> None:
        pass


@pytest.fixture
def clean_project(tmp_path: Path) -> Path:
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
  min_chapter_characters: 50
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
async def test_scoped_crawl_book_prefix_success_and_retry(
    tmp_path: Path, clean_project: Path
) -> None:
    books_root = tmp_path / "books"
    slug = "scoped-book"
    source_url = "https://www.piaotia.com/book/index.html"

    crawler = FiveChapterCrawler(CrawlSettings())

    result = await crawl_book(
        books_root=books_root,
        book_slug=slug,
        source_url=source_url,
        project_root=clean_project,
        style_name="general",
        scope_limit=3,
        chapter_delay_seconds=0.01,
        static_crawler_class=lambda settings: crawler,
        renderer_instance=DummyRenderer(),
    )

    assert result.status == OperationStatus.OK, result.reason

    paths = workspace_paths(books_root, slug)

    # 1. Catalog has exactly 3 entries
    catalog = load_yaml_model(paths.chapters, ChapterCatalog)
    assert len(catalog.chapters) == 3
    assert [c.chapter_id for c in catalog.chapters] == [1, 2, 3]

    # 2. State has exactly 3 entries, all completed
    state = load_yaml_model(paths.state, BookState)
    assert len(state.chapters) == 3
    assert [c.chapter_id for c in state.chapters] == [1, 2, 3]

    # 3. Exactly 3 raw files exist
    raw_files = list(paths.raw.glob("*.txt"))
    assert len(raw_files) == 3

    # 4. Scope record has 5 entries, selected_count == 3
    assert paths.source_scope.is_file()
    scope_rec = load_source_scope(paths.source_scope)
    assert isinstance(scope_rec, SourceScopeRecord)
    assert scope_rec.source_count == 5
    assert scope_rec.selected_count == 3
    assert scope_rec.selected_chapter_ids == [1, 2, 3]
    assert len(scope_rec.entries) == 5

    # 5. CrawlReport direct fields
    profile_src = load_active_crawl_profile(clean_project, paths.root, source_url)
    report = build_crawl_report(paths.root, profile_src.profile, CrawlSettings())
    assert report.discovered_count == 3
    assert report.selected_count == 3
    assert report.completed_count == 3
    assert report.source_discovered_count == 5
    assert report.scope == ApprovalScope.FULL
    assert report.scope_summary == "prefix 3 of 5"

    # 6. Retry skips valid raw files
    fetch_count_before = len(crawler.fetch_calls)
    retry_result = await crawl_book(
        books_root=books_root,
        book_slug=slug,
        source_url=source_url,
        project_root=clean_project,
        style_name="general",
        scope_limit=3,
        chapter_delay_seconds=0.01,
        static_crawler_class=lambda settings: crawler,
        renderer_instance=DummyRenderer(),
    )
    assert retry_result.status == OperationStatus.OK
    # No additional chapter fetches were made because raw files were all valid
    chapter_fetches_after = [
        c
        for c in crawler.fetch_calls[fetch_count_before:]
        if "c" in c and "index" not in c
    ]
    assert len(chapter_fetches_after) == 0


@pytest.mark.asyncio
async def test_scoped_crawl_changed_source_blocks_without_overwriting(
    tmp_path: Path, clean_project: Path
) -> None:
    books_root = tmp_path / "books"
    slug = "changed-book"
    source_url = "https://www.piaotia.com/book/index.html"

    crawler = FiveChapterCrawler(CrawlSettings())

    res1 = await crawl_book(
        books_root=books_root,
        book_slug=slug,
        source_url=source_url,
        project_root=clean_project,
        style_name="general",
        scope_limit=3,
        chapter_delay_seconds=0.01,
        static_crawler_class=lambda settings: crawler,
        renderer_instance=DummyRenderer(),
    )
    assert res1.status == OperationStatus.OK

    paths = workspace_paths(books_root, slug)
    orig_scope = load_source_scope(paths.source_scope)

    # Now crawler reports changed source
    crawler.catalog_source = "changed"
    # Clear catalog to simulate re-discovery on retry
    from dich_truyen_agent.storage import atomic_write_yaml

    atomic_write_yaml(paths.chapters, ChapterCatalog(chapters=[]))

    res2 = await crawl_book(
        books_root=books_root,
        book_slug=slug,
        source_url=source_url,
        project_root=clean_project,
        style_name="general",
        scope_limit=3,
        chapter_delay_seconds=0.01,
        static_crawler_class=lambda settings: crawler,
        renderer_instance=DummyRenderer(),
    )
    assert res2.status == OperationStatus.BLOCKED
    assert "catalog-changed" in res2.reason or "digest" in res2.reason.lower()

    # Scope file was not overwritten
    current_scope = load_source_scope(paths.source_scope)
    assert current_scope.source_digest == orig_scope.source_digest


@pytest.mark.asyncio
async def test_scoped_crawl_source_gap_outside_selected_prefix_blocks(
    tmp_path: Path, clean_project: Path
) -> None:
    books_root = tmp_path / "books"
    slug = "gap-book"
    source_url = "https://www.piaotia.com/book/index.html"

    crawler = FiveChapterCrawler(CrawlSettings())
    crawler.catalog_source = "gap_outside"

    res = await crawl_book(
        books_root=books_root,
        book_slug=slug,
        source_url=source_url,
        project_root=clean_project,
        style_name="general",
        scope_limit=3,
        chapter_delay_seconds=0.01,
        static_crawler_class=lambda settings: crawler,
        renderer_instance=DummyRenderer(),
    )
    assert res.status == OperationStatus.BLOCKED
    assert "gap" in res.reason.lower()


@pytest.mark.asyncio
async def test_scoped_crawl_duplicate_url_blocks(
    tmp_path: Path, clean_project: Path
) -> None:
    books_root = tmp_path / "books"
    slug = "dup-book"
    source_url = "https://www.piaotia.com/book/index.html"

    crawler = FiveChapterCrawler(CrawlSettings())
    crawler.catalog_source = "duplicate_url"

    res = await crawl_book(
        books_root=books_root,
        book_slug=slug,
        source_url=source_url,
        project_root=clean_project,
        style_name="general",
        scope_limit=3,
        chapter_delay_seconds=0.01,
        static_crawler_class=lambda settings: crawler,
        renderer_instance=DummyRenderer(),
    )
    assert res.status == OperationStatus.BLOCKED
    assert "duplicate" in res.reason.lower()


@pytest.mark.asyncio
async def test_scoped_crawl_empty_discovery_blocks(
    tmp_path: Path, clean_project: Path
) -> None:
    books_root = tmp_path / "books"
    slug = "empty-book"
    source_url = "https://www.piaotia.com/book/index.html"

    crawler = FiveChapterCrawler(CrawlSettings())
    crawler.catalog_source = "empty"

    res = await crawl_book(
        books_root=books_root,
        book_slug=slug,
        source_url=source_url,
        project_root=clean_project,
        style_name="general",
        scope_limit=3,
        chapter_delay_seconds=0.01,
        static_crawler_class=lambda settings: crawler,
        renderer_instance=DummyRenderer(),
    )
    assert res.status == OperationStatus.BLOCKED
    assert "zero chapters" in res.reason.lower()


@pytest.mark.asyncio
async def test_scoped_crawl_limit_greater_than_source_count_blocks(
    tmp_path: Path, clean_project: Path
) -> None:
    books_root = tmp_path / "books"
    slug = "overlimit-book"
    source_url = "https://www.piaotia.com/book/index.html"

    crawler = FiveChapterCrawler(CrawlSettings())

    res = await crawl_book(
        books_root=books_root,
        book_slug=slug,
        source_url=source_url,
        project_root=clean_project,
        style_name="general",
        scope_limit=10,
        chapter_delay_seconds=0.01,
        static_crawler_class=lambda settings: crawler,
        renderer_instance=DummyRenderer(),
    )
    assert res.status == OperationStatus.BLOCKED
    assert "exceed" in res.reason.lower() or "source" in res.reason.lower()


@pytest.mark.asyncio
async def test_scoped_crawl_crash_recovery_rebuilds_catalog_from_scope(
    tmp_path: Path, clean_project: Path
) -> None:
    books_root = tmp_path / "books"
    slug = "recovery-book"
    source_url = "https://www.piaotia.com/book/index.html"

    crawler = FiveChapterCrawler(CrawlSettings())

    # Step 1: Initial successful crawl
    res1 = await crawl_book(
        books_root=books_root,
        book_slug=slug,
        source_url=source_url,
        project_root=clean_project,
        style_name="general",
        scope_limit=3,
        chapter_delay_seconds=0.01,
        static_crawler_class=lambda settings: crawler,
        renderer_instance=DummyRenderer(),
    )
    assert res1.status == OperationStatus.OK

    paths = workspace_paths(books_root, slug)
    from dich_truyen_agent.storage import atomic_write_yaml

    # Simulate crash by emptying chapters.yaml
    atomic_write_yaml(paths.chapters, ChapterCatalog(chapters=[]))

    # Crawler fails on index fetch
    class FailingIndexCrawler(FiveChapterCrawler):
        async def fetch(self, url: str):
            if "index" in url:
                import httpx

                raise httpx.ConnectError("Network offline")
            return await super().fetch(url)

    res2 = await crawl_book(
        books_root=books_root,
        book_slug=slug,
        source_url=source_url,
        project_root=clean_project,
        style_name="general",
        scope_limit=3,
        chapter_delay_seconds=0.01,
        static_crawler_class=lambda settings: FailingIndexCrawler(settings),
        renderer_instance=DummyRenderer(),
    )
    assert res2.status == OperationStatus.OK, res2.reason
    # Catalog was rebuilt from scope
    catalog = load_yaml_model(paths.chapters, ChapterCatalog)
    assert len(catalog.chapters) == 3


@pytest.mark.asyncio
async def test_scoped_crawl_nonempty_catalog_with_missing_scope_blocks(
    tmp_path: Path, clean_project: Path
) -> None:
    books_root = tmp_path / "books"
    slug = "missing-scope-book"
    source_url = "https://www.piaotia.com/book/index.html"

    crawler = FiveChapterCrawler(CrawlSettings())

    res1 = await crawl_book(
        books_root=books_root,
        book_slug=slug,
        source_url=source_url,
        project_root=clean_project,
        style_name="general",
        scope_limit=3,
        chapter_delay_seconds=0.01,
        static_crawler_class=lambda settings: crawler,
        renderer_instance=DummyRenderer(),
    )
    assert res1.status == OperationStatus.OK

    paths = workspace_paths(books_root, slug)
    paths.source_scope.unlink()

    res2 = await crawl_book(
        books_root=books_root,
        book_slug=slug,
        source_url=source_url,
        project_root=clean_project,
        style_name="general",
        scope_limit=3,
        chapter_delay_seconds=0.01,
        static_crawler_class=lambda settings: crawler,
        renderer_instance=DummyRenderer(),
    )
    assert res2.status == OperationStatus.BLOCKED
    assert "missing" in res2.reason.lower()


@pytest.mark.asyncio
async def test_scoped_crawl_incomplete_selected_raw_in_report(
    tmp_path: Path, clean_project: Path
) -> None:
    books_root = tmp_path / "books"
    slug = "incomplete-raw-book"
    source_url = "https://www.piaotia.com/book/index.html"

    crawler = FiveChapterCrawler(CrawlSettings())

    res1 = await crawl_book(
        books_root=books_root,
        book_slug=slug,
        source_url=source_url,
        project_root=clean_project,
        style_name="general",
        scope_limit=3,
        chapter_delay_seconds=0.01,
        static_crawler_class=lambda settings: crawler,
        renderer_instance=DummyRenderer(),
    )
    assert res1.status == OperationStatus.OK

    paths = workspace_paths(books_root, slug)
    # Delete one raw file
    raw_files = list(paths.raw.glob("*.txt"))
    raw_files[0].unlink()

    profile_src = load_active_crawl_profile(clean_project, paths.root, source_url)
    report = build_crawl_report(paths.root, profile_src.profile, CrawlSettings())
    assert any("raw file is missing" in b for b in report.blockers)


@pytest.mark.asyncio
async def test_legacy_crawl_unchanged_full_and_partial(
    tmp_path: Path, clean_project: Path
) -> None:
    books_root = tmp_path / "books"
    slug = "legacy-book"
    source_url = "https://www.piaotia.com/book/index.html"

    crawler = FiveChapterCrawler(CrawlSettings())

    # Full legacy crawl (no scope_limit)
    res = await crawl_book(
        books_root=books_root,
        book_slug=slug,
        source_url=source_url,
        project_root=clean_project,
        style_name="general",
        chapter_delay_seconds=0.01,
        static_crawler_class=lambda settings: crawler,
        renderer_instance=DummyRenderer(),
    )
    assert res.status == OperationStatus.OK

    paths = workspace_paths(books_root, slug)
    catalog = load_yaml_model(paths.chapters, ChapterCatalog)
    assert len(catalog.chapters) == 5
    assert not paths.source_scope.exists()

    profile_src = load_active_crawl_profile(clean_project, paths.root, source_url)
    report = build_crawl_report(paths.root, profile_src.profile, CrawlSettings())
    assert report.discovered_count == 5
    assert report.selected_count == 5
    assert report.source_discovered_count is None
    assert report.scope_summary is None
    assert report.scope == ApprovalScope.FULL

    # Partial max_chapters on legacy
    slug_partial = "legacy-partial"
    crawler2 = FiveChapterCrawler(CrawlSettings())
    res_partial = await crawl_book(
        books_root=books_root,
        book_slug=slug_partial,
        source_url=source_url,
        project_root=clean_project,
        style_name="general",
        max_chapters=2,
        chapter_delay_seconds=0.01,
        static_crawler_class=lambda settings: crawler2,
        renderer_instance=DummyRenderer(),
    )
    assert res_partial.status == OperationStatus.OK

    paths_partial = workspace_paths(books_root, slug_partial)
    catalog_partial = load_yaml_model(paths_partial.chapters, ChapterCatalog)
    assert len(catalog_partial.chapters) == 5
    report_partial = build_crawl_report(
        paths_partial.root,
        profile_src.profile,
        CrawlSettings(max_chapters=2),
    )
    assert report_partial.discovered_count == 5
    assert report_partial.selected_count == 2
    assert report_partial.scope == ApprovalScope.PARTIAL
