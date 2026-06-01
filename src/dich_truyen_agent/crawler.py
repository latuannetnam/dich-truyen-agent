from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

import chardet
import httpx
from bs4 import BeautifulSoup

from dich_truyen_agent.models import (
    ChapterCatalog,
    ChapterCatalogEntry,
    CrawlProfile,
    CrawlSettings,
    DiscoveredChapter,
    ExtractedChapter,
)
from dich_truyen_agent.paths import chapter_filename


def detect_html_meta_charset(raw_bytes: bytes) -> str | None:
    """Scan the first 4KB of raw bytes for HTML meta charset declarations."""
    prefix = raw_bytes[:4096].decode("ascii", errors="ignore")
    # Match <meta charset="utf-8">
    match = re.search(r'<meta\s+charset=["\']?([a-zA-Z0-9_-]+)["\']?', prefix, re.IGNORECASE)
    if match:
        return match.group(1).lower()
    # Match <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
    match = re.search(
        r'content=["\']?[^"\']*;[^"\']*charset=([a-zA-Z0-9_-]+)["\']?',
        prefix,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).lower()
    return None


def decode_html(
    raw_bytes: bytes,
    explicit_encoding: str | None = None,
    http_charset: str | None = None,
) -> tuple[str, str, str]:
    """Decode raw bytes into a string using standard encoding precedence.
    
    Returns (decoded_text, chosen_encoding, provenance).
    """
    if explicit_encoding:
        try:
            return raw_bytes.decode(explicit_encoding), explicit_encoding.lower(), "profile"
        except (LookupError, UnicodeDecodeError):
            pass

    if http_charset:
        try:
            return raw_bytes.decode(http_charset), http_charset.lower(), "http_header"
        except (LookupError, UnicodeDecodeError):
            pass

    meta_charset = detect_html_meta_charset(raw_bytes)
    if meta_charset:
        try:
            return raw_bytes.decode(meta_charset), meta_charset.lower(), "html_meta"
        except (LookupError, UnicodeDecodeError):
            pass

    # Use chardet for detection
    detected = chardet.detect(raw_bytes)
    detected_enc = detected.get("encoding")
    if detected_enc:
        try:
            return raw_bytes.decode(detected_enc), detected_enc.lower(), "chardet"
        except (LookupError, UnicodeDecodeError):
            pass

    # Fallback to standard Chinese encodings
    for enc in ("gb18030", "gbk", "utf-8"):
        try:
            return raw_bytes.decode(enc), enc.lower(), "fallback"
        except (LookupError, UnicodeDecodeError):
            pass

    return raw_bytes.decode("utf-8", errors="replace"), "utf-8", "fallback_replace"


CHINESE_NUMS = {
    "零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10, "百": 100, "千": 1000
}


def parse_chinese_numeral(s: str) -> int | None:
    """Parse a basic Chinese numeral string into an integer."""
    if not s:
        return None
    total = 0
    r = 0
    for char in s:
        if char not in CHINESE_NUMS:
            return None
        val = CHINESE_NUMS[char]
        if val >= 10:
            if val == 10 and r == 0:
                r = 1
            total += (r * val)
            r = 0
        else:
            r = val
    total += r
    return total


def parse_chapter_ordinal(title: str) -> int | None:
    """Extract a numeric chapter ordinal from title (both Arabic and Chinese numerals)."""
    # Try Arabic numerals first: e.g. "第123章", "第 123 章"
    match = re.search(r'第\s*(\d+)\s*[章回]', title)
    if match:
        return int(match.group(1))

    # Try Chinese numerals: e.g. "第一百二十三章"
    match = re.search(r'第\s*([零一二两三四五六七八九十百千]+)\s*[章回]', title)
    if match:
        parsed = parse_chinese_numeral(match.group(1))
        if parsed is not None:
            return parsed

    # Simple start-of-title Arabic numeral match: e.g. "123. Chapter Title"
    match = re.match(r'^\s*(\d+)\b', title)
    if match:
        return int(match.group(1))

    return None


def discover_catalog(html: str, base_url: str, profile: CrawlProfile) -> list[DiscoveredChapter]:
    """Parse HTML and extract ordered DiscoveredChapters using profile index selectors."""
    soup = BeautifulSoup(html, "lxml")
    links = soup.select(profile.index.chapter_link_selector)
    chapters = []
    for index, a in enumerate(links, start=1):
        original_title = a.get_text().strip()
        href = a.get("href", "")
        resolved_url = urljoin(base_url, href)

        # Generate a stable source ID from URL
        parsed = urlparse(resolved_url)
        source_id = parsed.path.strip("/")
        if not source_id:
            source_id = resolved_url

        parsed_ordinal = parse_chapter_ordinal(original_title)
        chapters.append(
            DiscoveredChapter(
                position=index,
                source_id=source_id,
                source_url=resolved_url,
                original_title=original_title,
                parsed_ordinal=parsed_ordinal,
            )
        )
    return chapters


def validate_discovered_catalog(chapters: list[DiscoveredChapter]) -> dict[str, list[str]]:
    """Validate discovered catalog and return blockers and warnings."""
    blockers = []
    warnings = []

    # Check duplicates in URLs
    urls = [c.source_url for c in chapters]
    duplicate_urls = {u for u in urls if urls.count(u) > 1}
    for u in duplicate_urls:
        blockers.append(f"duplicate source URL: {u}")

    # Check duplicates in Source IDs
    ids = [c.source_id for c in chapters]
    duplicate_ids = {i for i in ids if ids.count(i) > 1}
    for i in duplicate_ids:
        blockers.append(f"duplicate source ID: {i}")

    # Process ordinals
    ordinals = []
    for c in chapters:
        if c.parsed_ordinal is not None:
            ordinals.append(c.parsed_ordinal)

    if ordinals:
        # Check duplicate ordinals
        duplicate_ords = {o for o in ordinals if ordinals.count(o) > 1}
        for o in duplicate_ords:
            warnings.append(f"duplicate chapter ordinal: {o}")

        # Check numeric gaps
        min_ord, max_ord = min(ordinals), max(ordinals)
        expected = set(range(min_ord, max_ord + 1))
        actual = set(ordinals)
        gaps = expected - actual
        if gaps:
            if duplicate_ords:
                warnings.append(f"clear numeric chapter gaps: {sorted(list(gaps))}")
            else:
                blockers.append(f"clear numeric chapter gaps: {sorted(list(gaps))}")

        # Check ordering
        is_sorted = all(ordinals[i] <= ordinals[i+1] for i in range(len(ordinals)-1))
        if not is_sorted:
            warnings.append("chapter ordinals are not strictly increasing")

    missing_ord_count = len(chapters) - len(ordinals)
    if missing_ord_count > 0 and len(ordinals) > 0:
        warnings.append(f"{missing_ord_count} chapters do not have parsed ordinals")

    return {"blockers": blockers, "warnings": warnings}


def to_chapter_catalog(chapters: list[DiscoveredChapter]) -> ChapterCatalog:
    """Convert discovered chapters into a validated ChapterCatalog."""
    entries = []
    for c in chapters:
        filename = chapter_filename(c.position, c.original_title)
        # Extract slug: chapter_filename is f"{chapter_id:04d}-{slug}.txt"
        slug = filename[5:-4]
        entries.append(
            ChapterCatalogEntry(
                chapter_id=c.position,
                slug=slug,
                source_url=c.source_url,
                original_title=c.original_title,
                raw_filename=filename,
                translation_filename=filename,
            )
        )
    return ChapterCatalog(chapters=entries)


def extract_chapter(
    html: str,
    source_url: str,
    profile: CrawlProfile,
    encoding_info: tuple[str, str] = ("utf-8", "fallback"),
) -> ExtractedChapter:
    """Parse HTML and extract cleaned title and content based on profile chapter selectors."""
    soup = BeautifulSoup(html, "lxml")

    # Title extraction
    title_elem = soup.select_one(profile.chapter.title_selector)
    if not title_elem:
        raise ValueError(f"Title selector {profile.chapter.title_selector!r} not found or empty")
    title = title_elem.get_text().strip()

    # Content extraction
    content_elem = soup.select_one(profile.chapter.content_selector)
    if not content_elem:
        raise ValueError(f"Content selector {profile.chapter.content_selector!r} not found")

    # Remove script and unwanted tags
    for selector in profile.chapter.remove_selectors:
        for elem in content_elem.select(selector):
            elem.decompose()

    # Format paragraph spacing
    for br in content_elem.find_all("br"):
        br.replace_with("\n")
    for p in content_elem.find_all(["p", "div"]):
        p.append("\n")

    text = content_elem.get_text()

    # Normalize paragraph structure
    lines = []
    for line in text.splitlines():
        line_str = line.strip()
        if line_str:
            lines.append(line_str)
    cleaned_text = "\n\n".join(lines)

    min_chars = profile.validation.min_chapter_characters
    if len(cleaned_text) < min_chars:
        raise ValueError(
            f"Extracted content length ({len(cleaned_text)}) is below threshold "
            f"({min_chars})"
        )

    return ExtractedChapter(
        title=title,
        text=cleaned_text,
        source_url=source_url,
        encoding=encoding_info[0],
        encoding_source=encoding_info[1],
    )


class StaticCrawler:
    """Deterministic HTTP static HTML fetcher."""

    def __init__(self, settings: CrawlSettings):
        self.settings = settings
        headers = {"User-Agent": settings.user_agent}
        self.client = httpx.AsyncClient(
            headers=headers,
            follow_redirects=True,
            timeout=settings.timeout_seconds,
        )

    async def close(self) -> None:
        await self.client.aclose()

    async def fetch(self, url: str) -> tuple[bytes, str | None]:
        """Fetch bytes and headers from a URL.
        
        Returns (raw_bytes, http_charset).
        """
        response = await self.client.get(url)
        response.raise_for_status()
        
        # Determine charset from response headers
        http_charset = None
        content_type = response.headers.get("content-type", "")
        if "charset=" in content_type.lower():
            try:
                http_charset = content_type.split("charset=")[-1].strip().lower()
            except Exception:
                pass
        return response.content, http_charset
