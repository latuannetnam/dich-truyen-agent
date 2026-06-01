import pytest

from dich_truyen_agent.crawler import (
    decode_html,
    detect_html_meta_charset,
    discover_catalog,
    extract_chapter,
    parse_chapter_ordinal,
    to_chapter_catalog,
    validate_discovered_catalog,
)
from dich_truyen_agent.models import (
    CrawlChapterProfile,
    CrawlEncodingProfile,
    CrawlIndexProfile,
    CrawlProfile,
    CrawlValidationProfile,
    DiscoveredChapter,
)


def test_detect_html_meta_charset() -> None:
    # 1. Standard meta charset
    html1 = b'<html><head><meta charset="utf-8"></head></html>'
    assert detect_html_meta_charset(html1) == "utf-8"

    # 2. Capitalization and quotes
    html2 = b"<html><head><META CHARSET='GBK'></head></html>"
    assert detect_html_meta_charset(html2) == "gbk"

    # 3. Http-equiv Content-Type meta
    html3 = b'<html><head><meta http-equiv="Content-Type" content="text/html; charset=gb2312"></head></html>'
    assert detect_html_meta_charset(html3) == "gb2312"

    # 4. None present
    html4 = b"<html><head></head></html>"
    assert detect_html_meta_charset(html4) is None


def test_decode_html_precedence() -> None:
    chinese_text = "第一章 测试"
    gbk_bytes = chinese_text.encode("gbk")

    # 1. Explicit profile override wins
    text, enc, prov = decode_html(gbk_bytes, explicit_encoding="gbk", http_charset="utf-8")
    assert text == chinese_text
    assert enc == "gbk"
    assert prov == "profile"

    # 2. HTTP charset wins over meta and below
    text, enc, prov = decode_html(gbk_bytes, http_charset="gbk")
    assert text == chinese_text
    assert enc == "gbk"
    assert prov == "http_header"

    # 3. HTML meta charset wins over chardet
    meta_html = f'<html><head><meta charset="gbk"></head><body>{chinese_text}</body></html>'
    meta_bytes = meta_html.encode("gbk")
    text, enc, prov = decode_html(meta_bytes)
    assert chinese_text in text
    assert enc == "gbk"
    assert prov == "html_meta"

    # 4. Fallback works
    text, enc, prov = decode_html(gbk_bytes)
    assert text == chinese_text
    assert enc in ("gbk", "gb18030")  # standard fallbacks or chardet
    assert prov in ("chardet", "fallback")


@pytest.mark.parametrize(
    "title,expected",
    [
        ("第1章 开启", 1),
        ("第123章 开启", 123),
        ("第 123 章 开启", 123),
        ("第一章 开启", 1),
        ("第十章 开启", 10),
        ("第一百二十三章 开启", 123),
        ("第两百章 开启", 200),
        ("123. 开启", 123),
        ("No ordinal title", None),
    ],
)
def test_parse_chapter_ordinal(title: str, expected: int | None) -> None:
    assert parse_chapter_ordinal(title) == expected


@pytest.fixture
def sample_profile() -> CrawlProfile:
    return CrawlProfile(
        domain="example.com",
        index=CrawlIndexProfile(
            chapter_link_selector=".chapters a",
        ),
        chapter=CrawlChapterProfile(
            title_selector="h1",
            content_selector="#content",
            remove_selectors=["script", ".navigation"],
        ),
        encoding=CrawlEncodingProfile(index="utf-8", chapter="utf-8"),
        validation=CrawlValidationProfile(min_chapter_characters=10),
    )


def test_discover_catalog(sample_profile: CrawlProfile) -> None:
    html = """
    <html>
      <body>
        <div class="chapters">
          <a href="c1.html">第一章 开启</a>
          <a href="/c2.html">第二章 过程</a>
          <a href="https://example.com/c3.html">第三章 结尾</a>
        </div>
      </body>
    </html>
    """
    chapters = discover_catalog(html, "https://example.com/index.html", sample_profile)
    assert len(chapters) == 3
    assert chapters[0].position == 1
    assert chapters[0].original_title == "第一章 开启"
    assert chapters[0].source_url == "https://example.com/c1.html"
    assert chapters[0].source_id == "c1.html"
    assert chapters[0].parsed_ordinal == 1

    assert chapters[1].source_url == "https://example.com/c2.html"
    assert chapters[1].source_id == "c2.html"


def test_validate_discovered_catalog() -> None:
    # 1. Perfectly valid catalog
    valid = [
        DiscoveredChapter(position=1, source_id="c1", source_url="http://a/1", original_title="第一章", parsed_ordinal=1),
        DiscoveredChapter(position=2, source_id="c2", source_url="http://a/2", original_title="第二章", parsed_ordinal=2),
    ]
    res = validate_discovered_catalog(valid)
    assert not res["blockers"]
    assert not res["warnings"]

    # 2. Duplicate source URL / ID
    dup = [
        DiscoveredChapter(position=1, source_id="c1", source_url="http://a/1", original_title="第一章", parsed_ordinal=1),
        DiscoveredChapter(position=2, source_id="c1", source_url="http://a/1", original_title="第二章", parsed_ordinal=2),
    ]
    res = validate_discovered_catalog(dup)
    assert len(res["blockers"]) == 2  # duplicate url and duplicate ID

    # 3. Numeric gaps in ordinals
    gap = [
        DiscoveredChapter(position=1, source_id="c1", source_url="http://a/1", original_title="第一章", parsed_ordinal=1),
        DiscoveredChapter(position=2, source_id="c2", source_url="http://a/2", original_title="第三章", parsed_ordinal=3),
    ]
    res = validate_discovered_catalog(gap)
    assert any("gaps" in b for b in res["blockers"])

    # 4. Out of order warning
    unordered = [
        DiscoveredChapter(position=1, source_id="c1", source_url="http://a/1", original_title="第二章", parsed_ordinal=2),
        DiscoveredChapter(position=2, source_id="c2", source_url="http://a/2", original_title="第一章", parsed_ordinal=1),
    ]
    res = validate_discovered_catalog(unordered)
    assert not res["blockers"]
    assert any("increasing" in w for w in res["warnings"])


def test_to_chapter_catalog() -> None:
    chapters = [
        DiscoveredChapter(position=1, source_id="c1", source_url="http://a/1", original_title="第一章 开启", parsed_ordinal=1),
    ]
    catalog = to_chapter_catalog(chapters)
    assert len(catalog.chapters) == 1
    assert catalog.chapters[0].chapter_id == 1
    assert catalog.chapters[0].slug == "chuong-0001"  # ASCII fallback for "第一章 开启" is empty or slugified
    assert catalog.chapters[0].raw_filename == "0001-chuong-0001.txt"
    assert catalog.chapters[0].translation_filename == "0001-chuong-0001.txt"


def test_extract_chapter(sample_profile: CrawlProfile) -> None:
    html = """
    <html>
      <body>
        <h1>Title of Chapter</h1>
        <div id="content">
          <script>console.log("bad");</script>
          <p>Line 1 of content.</p>
          <br>
          Line 2 of content.
          <div class="navigation">Skip this</div>
        </div>
      </body>
    </html>
    """
    extracted = extract_chapter(html, "http://a/1", sample_profile)
    assert extracted.title == "Title of Chapter"
    assert "Line 1 of content." in extracted.text
    assert "Line 2 of content." in extracted.text
    assert "console.log" not in extracted.text
    assert "Skip this" not in extracted.text
    # Paragraph structure check (should split with newlines)
    assert "\n\n" in extracted.text


def test_extract_chapter_validation_threshold(sample_profile: CrawlProfile) -> None:
    # Text is too short (less than 10 characters)
    html = """
    <html>
      <body>
        <h1>Title</h1>
        <div id="content">Short</div>
      </body>
    </html>
    """
    with pytest.raises(ValueError, match="threshold"):
        extract_chapter(html, "http://a/1", sample_profile)
