from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4


@dataclass(frozen=True)
class WorkspacePaths:
    root: Path
    book: Path
    chapters: Path
    state: Path
    style: Path
    raw: Path
    translations: Path
    staging: Path
    reports: Path
    results: Path
    checkpoints: Path
    exports: Path

    @property
    def stage_directories(self) -> tuple[Path, ...]:
        return (
            self.raw,
            self.translations,
            self.staging,
            self.reports,
            self.results,
            self.checkpoints,
            self.exports,
        )

    def checkpoint(self, checkpoint_type: str) -> Path:
        return self.checkpoints / f"{checkpoint_type}.yaml"


def _is_beneath(root: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def validate_book_slug(books_root: Path, book_slug: str) -> Path:
    if (
        not book_slug
        or book_slug in {".", ".."}
        or "/" in book_slug
        or "\\" in book_slug
        or Path(book_slug).is_absolute()
    ):
        raise ValueError(f"invalid book slug: {book_slug!r}")
    target = books_root / book_slug
    if not _is_beneath(books_root, target):
        raise ValueError(f"book slug escapes books root: {book_slug!r}")
    return target


def validate_workspace_relative_path(workspace_root: Path, relative_path: str) -> Path:
    candidate_path = Path(relative_path)
    if not relative_path or candidate_path.is_absolute() or ".." in candidate_path.parts:
        raise ValueError(f"path must stay workspace-relative: {relative_path!r}")
    candidate = workspace_root / candidate_path
    if not _is_beneath(workspace_root, candidate):
        raise ValueError(f"path escapes workspace: {relative_path!r}")
    return candidate


def workspace_paths(books_root: Path, book_slug: str) -> WorkspacePaths:
    root = validate_book_slug(books_root, book_slug)
    reports = root / "reports"
    return WorkspacePaths(
        root=root,
        book=root / "book.yaml",
        chapters=root / "chapters.yaml",
        state=root / "state.yaml",
        style=root / "style.yaml",
        raw=root / "raw",
        translations=root / "translations",
        staging=root / "staging",
        reports=reports,
        results=reports / "results",
        checkpoints=root / "checkpoints",
        exports=root / "exports",
    )


def chapter_filename(chapter_id: int, title: str) -> str:
    if chapter_id <= 0:
        raise ValueError("chapter_id must be positive")
    normalized = unicodedata.normalize("NFKD", title)
    ascii_title = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_title).strip("-")
    if not slug:
        slug = f"chuong-{chapter_id:04d}"
    return f"{chapter_id:04d}-{slug}.txt"


def temp_sibling_path(path: Path) -> Path:
    return path.with_name(f".{path.name}.{uuid4().hex}.tmp")
