from __future__ import annotations

import pytest

from dich_truyen_agent.models import (
    ChapterCatalog,
    ChapterCatalogEntry,
    DiscoveredChapter,
    SourceScopeRecord,
)
from dich_truyen_agent.paths import chapter_filename
from dich_truyen_agent.scope import (
    ScopeValidationResult,
    build_source_scope,
    compute_source_digest,
    load_source_scope,
    save_source_scope,
    validate_scope_catalog,
)


def make_five_discovered() -> list[DiscoveredChapter]:
    return [
        DiscoveredChapter(
            position=i,
            source_id=f"ch-{i}",
            source_url=f"https://example.com/novel/ch-{i}.html",
            original_title=f"第{i}章 章节{i}",
            parsed_ordinal=i,
        )
        for i in range(1, 6)
    ]


def test_build_source_scope_prefix() -> None:
    discovered = make_five_discovered()
    source_url = "https://example.com/novel/index.html"
    record = build_source_scope(discovered=discovered, source_url=source_url, limit=3)

    assert record.source_url == source_url
    assert record.mode == "prefix"
    assert record.requested_limit == 3
    assert record.source_count == 5
    assert record.selected_count == 3
    assert record.selected_chapter_ids == [1, 2, 3]
    assert record.selected_urls == [
        "https://example.com/novel/ch-1.html",
        "https://example.com/novel/ch-2.html",
        "https://example.com/novel/ch-3.html",
    ]
    assert record.source_digest == compute_source_digest(discovered)
    assert len(record.entries) == 5


def test_build_source_scope_full() -> None:
    discovered = make_five_discovered()
    source_url = "https://example.com/novel/index.html"
    record = build_source_scope(
        discovered=discovered, source_url=source_url, limit=None
    )

    assert record.source_url == source_url
    assert record.mode == "full"
    assert record.requested_limit is None
    assert record.source_count == 5
    assert record.selected_count == 5
    assert record.selected_chapter_ids == [1, 2, 3, 4, 5]
    assert record.selected_urls == [c.source_url for c in discovered]
    assert record.source_digest == compute_source_digest(discovered)
    assert len(record.entries) == 5


@pytest.mark.parametrize(
    "case,limit_val,mod_fn",
    [
        ("zero_limit", 0, None),
        ("negative_limit", -1, None),
        ("greater_than_count", 6, None),
        ("empty_discovery", None, lambda chapters: []),
        (
            "duplicate_url",
            3,
            lambda chapters: [
                DiscoveredChapter(
                    position=c.position,
                    source_id=c.source_id,
                    source_url=chapters[0].source_url
                    if c.position == 2
                    else c.source_url,
                    original_title=c.original_title,
                    parsed_ordinal=c.parsed_ordinal,
                )
                for c in chapters
            ],
        ),
        (
            "numeric_gap",
            3,
            lambda chapters: [
                DiscoveredChapter(
                    position=c.position,
                    source_id=c.source_id,
                    source_url=c.source_url,
                    original_title=f"第{c.position if c.position < 3 else c.position + 1}章 章节",
                    parsed_ordinal=c.position if c.position < 3 else c.position + 1,
                )
                for c in chapters
            ],
        ),
    ],
)
def test_build_source_scope_rejected_inputs(
    case: str, limit_val: int | None, mod_fn
) -> None:
    discovered = make_five_discovered()
    if mod_fn is not None:
        discovered = mod_fn(discovered)
    source_url = "https://example.com/novel/index.html"
    with pytest.raises(ValueError):
        build_source_scope(
            discovered=discovered, source_url=source_url, limit=limit_val
        )


def test_digest_changes_on_title_url_or_order() -> None:
    base = make_five_discovered()
    base_digest = compute_source_digest(base)

    # Changed title
    ch_title = [
        DiscoveredChapter(
            position=c.position,
            source_id=c.source_id,
            source_url=c.source_url,
            original_title=c.original_title + "_mod"
            if c.position == 1
            else c.original_title,
            parsed_ordinal=c.parsed_ordinal,
        )
        for c in base
    ]
    assert compute_source_digest(ch_title) != base_digest

    # Changed URL
    ch_url = [
        DiscoveredChapter(
            position=c.position,
            source_id=c.source_id,
            source_url="https://example.com/other.html"
            if c.position == 1
            else c.source_url,
            original_title=c.original_title,
            parsed_ordinal=c.parsed_ordinal,
        )
        for c in base
    ]
    assert compute_source_digest(ch_url) != base_digest

    # Changed order (swap position 1 and 2)
    ch_order = [base[1], base[0], base[2], base[3], base[4]]
    assert compute_source_digest(ch_order) != base_digest


def make_catalog_for_scope(record: SourceScopeRecord) -> ChapterCatalog:
    entries = []
    for cid in record.selected_chapter_ids:
        entry = record.entries[cid - 1]
        filename = chapter_filename(cid, entry.original_title)
        slug = filename[5:-4]
        entries.append(
            ChapterCatalogEntry(
                chapter_id=cid,
                slug=slug,
                source_url=entry.source_url,
                original_title=entry.original_title,
                raw_filename=filename,
                translation_filename=filename,
            )
        )
    return ChapterCatalog(chapters=entries)


def test_validate_scope_catalog_matching() -> None:
    discovered = make_five_discovered()
    source_url = "https://example.com/novel/index.html"
    record = build_source_scope(discovered=discovered, source_url=source_url, limit=3)
    catalog = make_catalog_for_scope(record)

    result = validate_scope_catalog(record, catalog)
    assert isinstance(result, ScopeValidationResult)
    assert result.is_valid
    assert result.reason is None


def test_validate_scope_catalog_mismatches() -> None:
    discovered = make_five_discovered()
    source_url = "https://example.com/novel/index.html"
    record = build_source_scope(discovered=discovered, source_url=source_url, limit=3)
    valid_catalog = make_catalog_for_scope(record)

    # Mismatched chapter IDs / count
    bad_catalog_ids = ChapterCatalog(chapters=valid_catalog.chapters[:2])
    res = validate_scope_catalog(record, bad_catalog_ids)
    assert not res.is_valid
    assert "count" in res.reason.lower() or "id" in res.reason.lower()

    # Mismatched URL
    bad_entries = list(valid_catalog.chapters)
    bad_entries[0] = ChapterCatalogEntry(
        chapter_id=bad_entries[0].chapter_id,
        slug=bad_entries[0].slug,
        source_url="https://example.com/different.html",
        original_title=bad_entries[0].original_title,
        raw_filename=bad_entries[0].raw_filename,
        translation_filename=bad_entries[0].translation_filename,
    )
    bad_catalog_url = ChapterCatalog(chapters=bad_entries)
    res = validate_scope_catalog(record, bad_catalog_url)
    assert not res.is_valid
    assert "url" in res.reason.lower()

    # Mismatched title
    bad_entries2 = list(valid_catalog.chapters)
    bad_entries2[0] = ChapterCatalogEntry(
        chapter_id=bad_entries2[0].chapter_id,
        slug=bad_entries2[0].slug,
        source_url=bad_entries2[0].source_url,
        original_title="Tampered title",
        raw_filename=bad_entries2[0].raw_filename,
        translation_filename=bad_entries2[0].translation_filename,
    )
    bad_catalog_title = ChapterCatalog(chapters=bad_entries2)
    res = validate_scope_catalog(record, bad_catalog_title)
    assert not res.is_valid
    assert "title" in res.reason.lower()


def test_save_and_load_source_scope(tmp_path) -> None:
    discovered = make_five_discovered()
    source_url = "https://example.com/novel/index.html"
    record = build_source_scope(discovered=discovered, source_url=source_url, limit=3)

    scope_path = tmp_path / "reports" / "source-scope.yaml"
    save_source_scope(scope_path, record)
    assert scope_path.is_file()

    loaded = load_source_scope(scope_path)
    assert loaded == record
