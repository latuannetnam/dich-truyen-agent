from pathlib import Path

import httpx
import pytest

from dich_truyen_agent.crawl_batch import crawl_book, detect_anti_bot_blocking, is_recoverable_exception
from dich_truyen_agent.models import BookState, CrawlSettings, OperationStatus, StageStatus
from dich_truyen_agent.paths import workspace_paths
from dich_truyen_agent.storage import load_yaml_model


def test_is_recoverable_exception() -> None:
    assert is_recoverable_exception(httpx.TimeoutException("timeout")) is True
    assert is_recoverable_exception(httpx.ConnectError("connect")) is True
    assert is_recoverable_exception(httpx.HTTPStatusError("500", request=None, response=httpx.Response(500))) is True
    assert is_recoverable_exception(httpx.HTTPStatusError("404", request=None, response=httpx.Response(404))) is False


def test_detect_anti_bot_blocking() -> None:
    html_block = "<html><body>We have detected unusual activity. Cloudflare protection.</body></html>"
    html_normal = "<html><body><h1>Chapter 1</h1><p>Content text is here</p></body></html>"

    assert detect_anti_bot_blocking(html_block) is not None
    assert detect_anti_bot_blocking(html_normal) is None
    assert detect_anti_bot_blocking("", 403) is not None


# Test spies and mock injectables
class FakeStaticCrawler:
    def __init__(self, settings: CrawlSettings):
        self.settings = settings
        self.fetch_calls = []
        self.url_attempts = {}

    async def fetch(self, url: str) -> tuple[bytes, str | None]:
        self.fetch_calls.append(url)
        self.url_attempts[url] = self.url_attempts.get(url, 0) + 1
        # Mock index or chapter responses depending on URL pattern
        if "index" in url:
            html = """
            <html>
              <head><title>My Book - 飘天文学</title></head>
              <body>
                <div class="centent">
                  <ul>
                    <li><a href="c1.html">第一章 Title 1</a></li>
                    <li><a href="c2.html">第二章 Title 2</a></li>
                    <li><a href="c3.html">第三章 Title 3</a></li>
                  </ul>
                </div>
              </body>
            </html>
            """
            return html.encode("gbk"), "gbk"
        elif "c1" in url:
            html = "<h1>Title 1</h1><div id='content'>Content of chapter 1. This contains more than one hundred characters to bypass the character validation checks. Long text here... Long text here... Long text here... Long text here...</div>"
            return html.encode("gbk"), "gbk"
        elif "c2" in url:
            # Chapter 2 triggers error on first fetch, succeed on retry
            if self.url_attempts[url] < 3:
                raise httpx.TimeoutException("Recoverable timeout")
            html = "<h1>Title 2</h1><div id='content'>Content of chapter 2. This contains more than one hundred characters to bypass the character validation checks. Long text here... Long text here... Long text here... Long text here...</div>"
            return html.encode("gbk"), "gbk"
        elif "c3" in url:
            # Non-recoverable error
            raise httpx.HTTPStatusError("404 Not Found", request=None, response=httpx.Response(404))

        raise ValueError("Unknown URL")

    async def close(self) -> None:
        pass


class FakeRenderer:
    def __init__(self) -> None:
        self.render_calls = []

    async def render(self, url: str, profile, *, purpose: str = "chapter") -> str:
        self.render_calls.append((url, profile.domain, purpose))
        return "<h1>JS Title</h1><div id='content'>JS Content of chapter JS. This contains more than one hundred characters to bypass the character validation checks. Long text here... Long text here... Long text here... Long text here...</div>"


@pytest.fixture
def clean_project(tmp_path: Path) -> Path:
    project_root = tmp_path / "project"
    project_root.mkdir()
    profile_dir = project_root / "templates" / "crawl_profiles"
    profile_dir.mkdir(parents=True)
    style_dir = project_root / "templates" / "styles"
    style_dir.mkdir(parents=True)

    # Write dummy shared profile
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

    # Write dummy style template
    style_content = """
name: "tien_hiep"
description: "Tien Hiep template"
guidelines: ["Use Vietnamese Sino-Vietnamese translations"]
vocabulary: {}
tone: "classical"
examples: []
"""
    (style_dir / "tien_hiep.yaml").write_text(style_content, encoding="utf-8")

    return project_root


@pytest.mark.asyncio
async def test_crawl_book_initializes_and_downloads_full_or_limited_scope(
    tmp_path: Path, clean_project: Path
) -> None:
    books_root = tmp_path / "books"
    slug = "test-book"
    
    sleep_calls = []
    async def mock_sleep(secs: float) -> None:
        sleep_calls.append(secs)

    crawler = FakeStaticCrawler(CrawlSettings())

    # Limited crawl to 2 chapters
    res = await crawl_book(
        books_root=books_root,
        book_slug=slug,
        source_url="https://www.piaotia.com/html/8/8717/index.html",
        project_root=clean_project,
        max_chapters=2,
        chapter_delay_seconds=3.0,
        sleeper_fn=mock_sleep,
        static_crawler_class=lambda settings: crawler,
    )

    assert res.status is OperationStatus.OK
    # Should download Chapter 1 and Chapter 2. (Chapter 2 succeeded after retry)
    assert res.progress is not None
    assert res.progress.completed == 2
    assert res.progress.total == 2
    
    paths = workspace_paths(books_root, slug)
    assert paths.chapters.is_file()
    assert paths.state.is_file()
    assert (paths.raw / "0001-title-1.txt").is_file()
    assert (paths.raw / "0002-title-2.txt").is_file()
    assert not (paths.raw / "0003-title-3.txt").exists()

    # Sleep check: should only sleep between chapter 1 and 2 (so exactly one delay sleep of 3.0, plus retry backoff sleeps)
    # Recoverable Timeout sleep on Chapter 2: backoff_seconds * (2 ** 0) = 1.0 (attempt 1) -> retry 1
    # Recoverable Timeout sleep on Chapter 2: backoff_seconds * (2 ** 1) = 2.0 (attempt 2) -> retry 2
    # Then succeeding on attempt 3. So sleeps should contain 1.0, 2.0 and 3.0 pacing sleep!
    assert 3.0 in sleep_calls
    assert 1.0 in sleep_calls
    assert 2.0 in sleep_calls


@pytest.mark.asyncio
async def test_crawl_book_stop_on_gap_and_resume(
    tmp_path: Path, clean_project: Path
) -> None:
    books_root = tmp_path / "books"
    slug = "gap-book"
    
    sleep_calls = []
    async def mock_sleep(secs: float) -> None:
        sleep_calls.append(secs)

    crawler = FakeStaticCrawler(CrawlSettings())

    # Full crawl including chapter 3 (which raises 404 non-recoverable error)
    res = await crawl_book(
        books_root=books_root,
        book_slug=slug,
        source_url="https://www.piaotia.com/html/8/8717/index.html",
        project_root=clean_project,
        max_chapters=3,
        chapter_delay_seconds=3.0,
        sleeper_fn=mock_sleep,
        static_crawler_class=lambda settings: crawler,
    )

    assert res.status is OperationStatus.ERROR
    assert "sequential crawl stopped due to non-recoverable error" in res.reason
    
    # Progress: Chapter 1 & 2 completed, Chapter 3 remains pending or error
    paths = workspace_paths(books_root, slug)
    state = load_yaml_model(paths.state, BookState)
    assert state.chapters[0].raw.status is StageStatus.COMPLETED
    assert state.chapters[1].raw.status is StageStatus.COMPLETED
    assert state.chapters[2].raw.status is StageStatus.ERROR

    # Now let's resume. Modify Chapter 3 mock behaviour by swapping crawler with a fully succeeding one
    class SucceedingCrawler:
        def __init__(self, settings: CrawlSettings):
            self.settings = settings
        async def fetch(self, url: str) -> tuple[bytes, str | None]:
            # Mock succeed on Chapter 3
            html = "<h1>Title 3</h1><div id='content'>Content of chapter 3. This contains more than one hundred characters to bypass the character validation checks. Long text here... Long text here... Long text here... Long text here...</div>"
            return html.encode("gbk"), "gbk"
        async def close(self) -> None:
            pass

    succeeding_crawler = SucceedingCrawler(CrawlSettings())
    res_resume = await crawl_book(
        books_root=books_root,
        book_slug=slug,
        source_url="https://www.piaotia.com/html/8/8717/index.html",
        project_root=clean_project,
        max_chapters=3,
        chapter_delay_seconds=3.0,
        sleeper_fn=mock_sleep,
        static_crawler_class=lambda settings: succeeding_crawler,
    )

    assert res_resume.status is OperationStatus.OK
    assert res_resume.progress is not None
    assert res_resume.progress.completed == 3
    assert (paths.raw / "0003-title-3.txt").is_file()


@pytest.mark.asyncio
async def test_crawl_book_passes_profile_and_purpose_to_browser_fallback(
    tmp_path: Path, clean_project: Path
) -> None:
    books_root = tmp_path / "books"
    slug = "browser-profile-book"

    async def no_sleep(seconds: float) -> None:
        del seconds

    class AntiBotIndexCrawler:
        def __init__(self, settings: CrawlSettings):
            self.settings = settings

        async def fetch(self, url: str) -> tuple[bytes, str | None]:
            if "index" in url:
                return b"<html><body>Cloudflare protection</body></html>", "utf-8"
            html = "<h1>Title 1</h1><div id='content'>Content of chapter 1. This contains more than one hundred characters to bypass the character validation checks. Long text here... Long text here... Long text here... Long text here...</div>"
            return html.encode("gbk"), "gbk"

        async def close(self) -> None:
            pass

    class IndexRenderer:
        def __init__(self) -> None:
            self.render_calls = []

        async def render(self, url: str, profile, *, purpose: str = "chapter") -> str:
            self.render_calls.append((url, profile.domain, purpose))
            return """
            <html>
              <head><title>My Book</title></head>
              <body>
                <div class="centent">
                  <ul><li><a href="c1.html">第一章 Title 1</a></li></ul>
                </div>
              </body>
            </html>
            """

        async def close(self) -> None:
            pass

    renderer = IndexRenderer()
    res = await crawl_book(
        books_root=books_root,
        book_slug=slug,
        source_url="https://www.piaotia.com/html/8/8717/index.html",
        project_root=clean_project,
        max_chapters=1,
        chapter_delay_seconds=0,
        sleeper_fn=no_sleep,
        static_crawler_class=AntiBotIndexCrawler,
        renderer_instance=renderer,
    )

    assert res.status is OperationStatus.OK
    assert renderer.render_calls == [
        ("https://www.piaotia.com/html/8/8717/index.html", "www.piaotia.com", "index")
    ]
