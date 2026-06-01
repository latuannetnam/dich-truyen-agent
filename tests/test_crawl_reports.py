from pathlib import Path

import pytest

from dich_truyen_agent.crawl_reports import approval_blockers, build_crawl_report
from dich_truyen_agent.crawler import CrawlProfile
from dich_truyen_agent.models import (
    BookMetadata,
    BookState,
    ChapterCatalog,
    ChapterCatalogEntry,
    ChapterState,
    CrawlChapterProfile,
    CrawlEncodingProfile,
    CrawlIndexProfile,
    CrawlSettings,
    CrawlValidationProfile,
    StageRecord,
    StageStatus,
)
from dich_truyen_agent.paths import workspace_paths
from dich_truyen_agent.storage import atomic_write_yaml
from dich_truyen_agent.workspace import initialize_workspace


@pytest.fixture
def workspace_with_raw(books_root: Path, style) -> Path:
    metadata = BookMetadata(
        book_slug="report-book",
        source_url="https://www.piaotia.com/html/8/8717/index.html",
        title="Report Book",
    )
    catalog = ChapterCatalog(
        chapters=[
            ChapterCatalogEntry(
                chapter_id=1,
                slug="c1",
                source_url="https://www.piaotia.com/c1.html",
                original_title="第一章 Title 1",
                raw_filename="0001-c1.txt",
                translation_filename="0001-c1.txt",
            )
        ]
    )
    initialize_workspace(books_root, metadata, catalog, style)
    paths = workspace_paths(books_root, metadata.book_slug)
    
    # Write a dummy raw file for chapter 1
    raw_file = paths.root / "raw" / "0001-c1.txt"
    raw_file.write_text(
        "Title 1\n\nContent of chapter 1. This contains more than one hundred characters of dummy text. "
        "Just trying to fill space to satisfy the minimum character validation threshold constraint in the profile. "
        "Adding even more characters to make sure it's long enough! Extra character check passed.",
        encoding="utf-8",
    )
    
    # Mark state as complete
    state = BookState(
        chapters=[
            ChapterState(
                chapter_id=1,
                raw=StageRecord(
                    status=StageStatus.COMPLETED,
                    canonical_path="raw/0001-c1.txt",
                    sha256="dummyhash",
                )
            )
        ]
    )
    atomic_write_yaml(paths.state, state)
    
    return paths.root


def test_build_crawl_report_success(workspace_with_raw: Path) -> None:
    profile = CrawlProfile(
        domain="www.piaotia.com",
        index=CrawlIndexProfile(chapter_link_selector=".chapters a"),
        chapter=CrawlChapterProfile(title_selector="h1", content_selector="#content"),
        encoding=CrawlEncodingProfile(index="gbk", chapter="gbk"),
        validation=CrawlValidationProfile(min_chapter_characters=50),
    )
    settings = CrawlSettings(max_chapters=0)
    
    report = build_crawl_report(workspace_with_raw, profile, settings)
    
    assert report.discovered_count == 1
    assert report.completed_count == 1
    assert report.failed_count == 0
    assert not approval_blockers(report)
    assert "1" in report.chapter_lengths
    assert report.chapter_lengths["1"] > 200
    
    # Check excerpt extraction
    assert "1" in report.excerpts
    assert "Title 1" in report.excerpts["1"]["beginning"]


def test_build_crawl_report_with_residue(workspace_with_raw: Path) -> None:
    # Inject script residue in the file
    paths = workspace_paths(workspace_with_raw.parent, workspace_with_raw.name)
    raw_file = paths.root / "raw" / "0001-c1.txt"
    raw_file.write_text("Title 1\n\nSome text with <script>console.log('garbage')</script> and cloudflare blockers.", encoding="utf-8")
    
    profile = CrawlProfile(
        domain="www.piaotia.com",
        index=CrawlIndexProfile(chapter_link_selector=".chapters a"),
        chapter=CrawlChapterProfile(title_selector="h1", content_selector="#content"),
        encoding=CrawlEncodingProfile(index="gbk", chapter="gbk"),
        validation=CrawlValidationProfile(min_chapter_characters=10),
    )
    settings = CrawlSettings(max_chapters=0)
    
    report = build_crawl_report(workspace_with_raw, profile, settings)
    assert "1" in report.suspicious_residue_findings
    assert "html_tags" in report.suspicious_residue_findings["1"]
    assert "script_residue" in report.suspicious_residue_findings["1"]
    assert "cloudflare_markers" in report.suspicious_residue_findings["1"]
    assert len(report.warnings) > 0
