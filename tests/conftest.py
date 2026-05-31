import atexit
import os
import shutil
import tempfile
from pathlib import Path
from uuid import uuid4

import _pytest.pathlib as pytest_pathlib
import _pytest.tmpdir as pytest_tmpdir
import pytest

from dich_truyen_agent.models import (
    BookMetadata,
    ChapterCatalog,
    ChapterCatalogEntry,
    TranslationStyle,
)

if os.name == "nt":
    _make_numbered_dir = pytest_pathlib.make_numbered_dir

    def _make_numbered_dir_with_inherited_acl(
        root: Path, prefix: str, mode: int = 0o700
    ) -> Path:
        # Owner-only Windows ACLs cannot be reopened by Codex's restricted token.
        del mode
        return _make_numbered_dir(root, prefix, mode=0o777)

    pytest_pathlib.make_numbered_dir = _make_numbered_dir_with_inherited_acl
    pytest_tmpdir.make_numbered_dir = _make_numbered_dir_with_inherited_acl

    def _getbasetemp_with_inherited_acl(
        self: pytest_tmpdir.TempPathFactory,
    ) -> Path:
        if self._basetemp is None:
            root = Path(tempfile.gettempdir()) / "codex-pytest"
            root.mkdir(exist_ok=True)
            basetemp = root / f"pytest-{os.getpid()}-{uuid4().hex}"
            basetemp.mkdir(mode=0o777)
            self._basetemp = basetemp.resolve()
            self._trace("new basetemp", self._basetemp)
            atexit.register(shutil.rmtree, self._basetemp, ignore_errors=True)
        return self._basetemp

    pytest_tmpdir.TempPathFactory.getbasetemp = _getbasetemp_with_inherited_acl


def pytest_configure(config: pytest.Config) -> None:
    if os.name == "nt":
        # Pytest's cache staging directory has the same owner-only ACL issue.
        config.cache._cachedir.mkdir(parents=True, exist_ok=True)


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
