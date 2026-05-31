from pathlib import Path

import pytest
from pydantic import ValidationError
from yaml.constructor import ConstructorError

from dich_truyen_agent.models import BookMetadata
from dich_truyen_agent.paths import (
    chapter_filename,
    temp_sibling_path,
    validate_book_slug,
    validate_workspace_relative_path,
)
from dich_truyen_agent.storage import (
    atomic_write_yaml,
    find_orphan_temp_files,
    load_yaml_model,
)


def metadata() -> BookMetadata:
    return BookMetadata(
        book_slug="demo-book",
        source_url="https://example.com/book",
        title="Demo",
    )


@pytest.mark.parametrize("slug", ["", ".", "..", "../escape", "nested/book", r"nested\book"])
def test_validate_book_slug_rejects_unsafe_values(tmp_path: Path, slug: str) -> None:
    with pytest.raises(ValueError):
        validate_book_slug(tmp_path, slug)


def test_relative_path_rejects_escape(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        validate_workspace_relative_path(tmp_path, "../escape.txt")


def test_chapter_filename_is_stable_and_has_ascii_fallback() -> None:
    assert chapter_filename(1, "Chuong Mo Dau") == "0001-chuong-mo-dau.txt"
    assert chapter_filename(2, "第一章") == "0002-chuong-0002.txt"


def test_atomic_yaml_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "book.yaml"
    atomic_write_yaml(path, metadata())
    assert load_yaml_model(path, BookMetadata) == metadata()


def test_load_yaml_rejects_unsafe_tag(tmp_path: Path) -> None:
    path = tmp_path / "unsafe.yaml"
    path.write_text("!!python/object:builtins.object {}\n", encoding="utf-8")
    with pytest.raises(ConstructorError):
        load_yaml_model(path, BookMetadata)


def test_load_yaml_rejects_malformed_model(tmp_path: Path) -> None:
    path = tmp_path / "malformed.yaml"
    path.write_text("title: Missing required fields\n", encoding="utf-8")
    with pytest.raises(ValidationError):
        load_yaml_model(path, BookMetadata)


def test_orphan_temp_is_reported_without_changing_canonical(tmp_path: Path) -> None:
    path = tmp_path / "book.yaml"
    atomic_write_yaml(path, metadata())
    original = path.read_bytes()
    orphan = temp_sibling_path(path)
    orphan.write_text("partial", encoding="utf-8")

    assert find_orphan_temp_files(tmp_path) == [orphan]
    assert orphan.exists()
    assert path.read_bytes() == original
