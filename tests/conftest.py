from pathlib import Path

import pytest

from dich_truyen_agent.models import (
    BookMetadata,
    ChapterCatalog,
    ChapterCatalogEntry,
    TranslationStyle,
)


@pytest.fixture
def books_root(tmp_path: Path) -> Path:
    return tmp_path / "books"


@pytest.fixture
def metadata() -> BookMetadata:
    return BookMetadata(
        book_slug="demo-book",
        source_url="https://example.com/book",
        title="Demo Book",
    )


@pytest.fixture
def catalog() -> ChapterCatalog:
    return ChapterCatalog(
        chapters=[
            ChapterCatalogEntry(
                chapter_id=1,
                slug="opening",
                source_url="https://example.com/chapter-1",
                original_title="Opening",
                raw_filename="0001-opening.txt",
                translation_filename="0001-opening.txt",
            )
        ]
    )


@pytest.fixture
def style() -> TranslationStyle:
    return TranslationStyle(
        name="test",
        description="Test style",
        guidelines=["Keep meaning"],
        vocabulary={},
        tone="formal",
        examples=[],
    )
