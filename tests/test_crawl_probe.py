from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import threading
from urllib.parse import urlparse
import pytest

from dich_truyen_agent.crawl_probe import probe_crawl_profile
from dich_truyen_agent.crawl_profiles import install_local_profile
from dich_truyen_agent.models import (
    BookMetadata,
    ChapterCatalog,
    ChapterCatalogEntry,
    CrawlChapterProfile,
    CrawlEncodingProfile,
    CrawlIndexProfile,
    CrawlProfile,
    CrawlValidationProfile,
    OperationStatus,
    TranslationStyle,
)
from dich_truyen_agent.paths import workspace_paths
from dich_truyen_agent.storage import atomic_write_yaml
from dich_truyen_agent.workspace import initialize_workspace


class MockCrawlHandler(BaseHTTPRequestHandler):
    pages: dict[str, tuple[int, dict[str, str], bytes]] = {}

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in self.pages:
            status, headers, content = self.pages[path]
            self.send_response(status)
            for k, v in headers.items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(content)
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")

    def log_message(self, format: str, *args) -> None:
        pass


@pytest.fixture
def mock_server():
    server = HTTPServer(("127.0.0.1", 0), MockCrawlHandler)
    host, port = server.server_address
    base_url = f"http://127.0.0.1:{port}"
    MockCrawlHandler.pages = {}
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield base_url, MockCrawlHandler.pages
    server.shutdown()
    server.server_close()


@pytest.fixture
def test_setup(tmp_path: Path, mock_server: tuple[str, dict]):
    base_url, pages = mock_server

    # Set up index page
    index_html = (
        '<html><body><div class="chapters">'
        f'<a href="{base_url}/c1.html">第1章 Chương 1</a>'
        f'<a href="{base_url}/c2.html">第2章 Chương 2</a>'
        f'<a href="{base_url}/c3.html">第3章 Chương 3</a>'
        '</div></body></html>'
    )
    pages["/index.html"] = (200, {"Content-Type": "text/html; charset=utf-8"}, index_html.encode("utf-8"))

    # Set up chapter pages
    for i in range(1, 4):
        ch_html = (
            f"<html><body><h1>第{i}章 Chương {i}</h1>"
            f'<div id="content">Nội dung chương {i} dài đủ điều kiện để vượt qua ngưỡng ký tự tối thiểu.'
            " Thêm chữ để đạt độ dài cần thiết của bài kiểm tra validation threshold.</div></body></html>"
        )
        pages[f"/c{i}.html"] = (200, {"Content-Type": "text/html; charset=utf-8"}, ch_html.encode("utf-8"))

    # Create workspace
    books_root = tmp_path / "books"
    metadata = BookMetadata(
        book_slug="probe-book",
        source_url=f"{base_url}/index.html",
        title="Probe Book",
    )
    catalog = ChapterCatalog(
        chapters=[
            ChapterCatalogEntry(
                chapter_id=1,
                slug="chuong-0001",
                source_url=f"{base_url}/c1.html",
                original_title="第1章 Chương 1",
                raw_filename="0001-chuong-0001.txt",
                translation_filename="0001-chuong-0001.txt",
            ),
            ChapterCatalogEntry(
                chapter_id=2,
                slug="chuong-0002",
                source_url=f"{base_url}/c2.html",
                original_title="第2章 Chương 2",
                raw_filename="0002-chuong-0002.txt",
                translation_filename="0002-chuong-0002.txt",
            ),
            ChapterCatalogEntry(
                chapter_id=3,
                slug="chuong-0003",
                source_url=f"{base_url}/c3.html",
                original_title="第3章 Chương 3",
                raw_filename="0003-chuong-0003.txt",
                translation_filename="0003-chuong-0003.txt",
            ),
        ]
    )
    style = TranslationStyle(
        name="test",
        description="desc",
        tone="formal",
        guidelines=[],
        vocabulary={},
        examples=[],
    )
    initialize_workspace(books_root, metadata, catalog, style)
    paths = workspace_paths(books_root, metadata.book_slug)

    # Valid candidate profile
    candidate_profile = CrawlProfile(
        domain="127.0.0.1",
        index=CrawlIndexProfile(chapter_link_selector=".chapters a"),
        chapter=CrawlChapterProfile(title_selector="h1", content_selector="#content"),
        encoding=CrawlEncodingProfile(index="utf-8", chapter="utf-8"),
        validation=CrawlValidationProfile(min_chapter_characters=20),
    )
    candidate_file = tmp_path / "candidate-profile.yaml"
    atomic_write_yaml(candidate_file, candidate_profile)

    return paths, candidate_file, candidate_profile, pages, base_url


def test_probe_success(test_setup) -> None:
    paths, candidate_file, _, _, _ = test_setup
    result = probe_crawl_profile(paths.root, candidate_file)
    assert result.status is OperationStatus.OK
    assert result.data["discovered_count"] == 3
    assert result.data["samples_checked"] == 3

    # Assert read-only: no profile override was written
    assert not (paths.root / "crawl-profile.yaml").exists()
    assert list(paths.raw.glob("*.txt")) == []


def test_probe_rejects_domain_mismatch(test_setup) -> None:
    paths, candidate_file, profile, _, _ = test_setup
    profile.domain = "other-domain.com"
    atomic_write_yaml(candidate_file, profile)

    result = probe_crawl_profile(paths.root, candidate_file)
    assert result.status is OperationStatus.BLOCKED
    assert "domain mismatch" in result.reason


def test_probe_rejects_empty_index_selector(test_setup) -> None:
    paths, candidate_file, profile, _, _ = test_setup
    profile.index.chapter_link_selector = ".nonexistent a"
    atomic_write_yaml(candidate_file, profile)

    result = probe_crawl_profile(paths.root, candidate_file)
    assert result.status is OperationStatus.BLOCKED
    assert "zero chapters" in result.reason


def test_probe_rejects_content_below_threshold(test_setup) -> None:
    paths, candidate_file, profile, _, _ = test_setup
    profile.validation.min_chapter_characters = 5000  # Higher than test chapters
    atomic_write_yaml(candidate_file, profile)

    result = probe_crawl_profile(paths.root, candidate_file)
    assert result.status is OperationStatus.BLOCKED
    assert "below threshold" in result.reason


def test_probe_rejects_changed_catalog_order(test_setup) -> None:
    paths, candidate_file, _, pages, base_url = test_setup
    before = paths.chapters.read_bytes()

    # Change order of links on index page
    reversed_index = (
        '<html><body><div class="chapters">'
        f'<a href="{base_url}/c3.html">第3章 Chương 3</a>'
        f'<a href="{base_url}/c2.html">第2章 Chương 2</a>'
        f'<a href="{base_url}/c1.html">第1章 Chương 1</a>'
        '</div></body></html>'
    )
    pages["/index.html"] = (200, {"Content-Type": "text/html; charset=utf-8"}, reversed_index.encode("utf-8"))

    result = probe_crawl_profile(paths.root, candidate_file)
    assert result.status is OperationStatus.BLOCKED
    assert "catalog-changed" in result.reason
    assert paths.chapters.read_bytes() == before


def test_install_local_profile_success(test_setup) -> None:
    paths, candidate_file, _, _, _ = test_setup
    result = install_local_profile(paths.root, candidate_file)
    assert result.status is OperationStatus.OK
    installed = paths.root / "crawl-profile.yaml"
    assert installed.is_file()


def test_install_local_profile_rejects_failing_candidate(test_setup) -> None:
    paths, candidate_file, profile, _, _ = test_setup
    profile.index.chapter_link_selector = ".broken-selector a"
    atomic_write_yaml(candidate_file, profile)

    result = install_local_profile(paths.root, candidate_file)
    assert result.status is OperationStatus.BLOCKED
    assert not (paths.root / "crawl-profile.yaml").exists()
