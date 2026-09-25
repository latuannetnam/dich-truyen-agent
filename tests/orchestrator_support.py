from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from dich_truyen_agent.checkpoints import approve_checkpoint
from dich_truyen_agent.models import (
    BookMetadata,
    BookState,
    ChapterCatalog,
    ChapterCatalogEntry,
    CheckpointType,
    StageRecord,
    StageStatus,
    TranslationStyle,
)
from dich_truyen_agent.paths import workspace_paths
from dich_truyen_agent.storage import atomic_write_yaml, load_yaml_model, sha256_file
from dich_truyen_agent.workspace import initialize_workspace


@dataclass
class WorkspaceFixture:
    root: Path
    catalog: Path
    state: Path
    book: Path
    style: Path
    report: Path
    raw_paths: list[Path]
    translation_paths: list[Path]

    def __fspath__(self) -> str:
        return str(self.root)

    def reload_state(self) -> BookState:
        return load_yaml_model(self.state, BookState)

    def reload_catalog(self) -> ChapterCatalog:
        return load_yaml_model(self.catalog, ChapterCatalog)

    def promote_first_translation(self, title: str = "Chương 1 Tiên Nhân Chỉ Lộ") -> None:
        trans_path = self.translation_paths[0]
        content = f"# {title}\n\nĐạo khả đạo, phi thường đạo.\n"
        trans_path.write_text(content, encoding="utf-8")

        state = self.reload_state()
        state.chapters[0].translation = StageRecord(
            status=StageStatus.COMPLETED,
            canonical_path=f"translations/{trans_path.name}",
            sha256=sha256_file(trans_path),
            updated_at=datetime.now(UTC),
        )
        atomic_write_yaml(self.state, state)


def create_two_chapter_catalog() -> ChapterCatalog:
    return ChapterCatalog(
        chapters=[
            ChapterCatalogEntry(
                chapter_id=1,
                slug="chuong-0001",
                source_url="http://example.com/1",
                original_title="第1章 仙人指路",
                raw_filename="0001-chuong-0001.txt",
                translation_filename="0001-chuong-0001.txt",
            ),
            ChapterCatalogEntry(
                chapter_id=2,
                slug="chuong-0002",
                source_url="http://example.com/2",
                original_title="第2章 炼气入体",
                raw_filename="0002-chuong-0002.txt",
                translation_filename="0002-chuong-0002.txt",
            ),
        ]
    )


def create_test_metadata(slug: str = "test-book") -> BookMetadata:
    return BookMetadata(
        book_slug=slug,
        title="Test Novel",
        source_url="http://example.com/book",
        author="Author",
    )


def create_test_style() -> TranslationStyle:
    return TranslationStyle(
        name="test-style",
        description="Test style description",
        tone="archaic",
        guidelines=["Keep meaning"],
        vocabulary={},
        examples=[],
    )


def build_initialized_workspace(
    tmp_path: Path,
    *,
    chapter_count: int = 2,
    slug: str = "test-book",
) -> WorkspaceFixture:
    books_root = tmp_path / "books"
    metadata = create_test_metadata(slug)
    style = create_test_style()

    entries = []
    for i in range(1, chapter_count + 1):
        entries.append(
            ChapterCatalogEntry(
                chapter_id=i,
                slug=f"chuong-{i:04d}",
                source_url=f"http://example.com/{i}",
                original_title=f"第{i}章 章节标题{i}",
                raw_filename=f"{i:04d}-chuong-{i:04d}.txt",
                translation_filename=f"{i:04d}-chuong-{i:04d}.txt",
            )
        )
    catalog = ChapterCatalog(chapters=entries)
    initialize_workspace(books_root, metadata, catalog, style)

    paths = workspace_paths(books_root, slug)
    raw_paths = [paths.raw / entry.raw_filename for entry in entries]
    translation_paths = [paths.translations / entry.translation_filename for entry in entries]
    report_path = paths.reports / "crawl.yaml"

    return WorkspaceFixture(
        root=paths.root,
        catalog=paths.chapters,
        state=paths.state,
        book=paths.book,
        style=paths.style,
        report=report_path,
        raw_paths=raw_paths,
        translation_paths=translation_paths,
    )


def build_crawl_approved_workspace(
    tmp_path: Path,
    *,
    chapter_count: int = 2,
    slug: str = "test-book",
) -> WorkspaceFixture:
    wf = build_initialized_workspace(tmp_path, chapter_count=chapter_count, slug=slug)

    # Write raw chapter files and mark COMPLETED in state
    state = wf.reload_state()
    rel_raws = []
    for i, raw_file in enumerate(wf.raw_paths, start=1):
        raw_file.write_text(f"Raw content for chapter {i}", encoding="utf-8")
        rel_raw = f"raw/{raw_file.name}"
        rel_raws.append(rel_raw)
        state.chapters[i - 1].raw = StageRecord(
            status=StageStatus.COMPLETED,
            canonical_path=rel_raw,
            sha256=sha256_file(raw_file),
            updated_at=datetime.now(UTC),
        )
    atomic_write_yaml(wf.state, state)

    # Write report and approve crawl checkpoint
    wf.report.parent.mkdir(parents=True, exist_ok=True)
    wf.report.write_text("crawl report ok", encoding="utf-8")
    approve_checkpoint(
        wf.root,
        CheckpointType.CRAWL_APPROVED,
        "reports/crawl.yaml",
        rel_raws,
    )

    return wf


def build_translated_workspace(
    tmp_path: Path,
    *,
    chapter_count: int = 2,
    slug: str = "test-book",
) -> WorkspaceFixture:
    wf = build_crawl_approved_workspace(tmp_path, chapter_count=chapter_count, slug=slug)
    state = wf.reload_state()

    for i, trans_file in enumerate(wf.translation_paths, start=1):
        content = f"# Chương {i} Tiêu Đề {i}\n\nNội dung chương {i} dịch mượt mà.\n"
        trans_file.write_text(content, encoding="utf-8")
        rel_trans = f"translations/{trans_file.name}"
        state.chapters[i - 1].translation = StageRecord(
            status=StageStatus.COMPLETED,
            canonical_path=rel_trans,
            sha256=sha256_file(trans_file),
            updated_at=datetime.now(UTC),
        )
    atomic_write_yaml(wf.state, state)
    return wf


def build_qa_approved_workspace(
    tmp_path: Path,
    *,
    chapter_count: int = 2,
    slug: str = "test-book",
) -> WorkspaceFixture:
    wf = build_translated_workspace(tmp_path, chapter_count=chapter_count, slug=slug)
    paths = workspace_paths(wf.root.parent, wf.root.name)

    qa_report = paths.reports / "qa-report.yaml"
    qa_report.parent.mkdir(parents=True, exist_ok=True)
    qa_report.write_text("qa check ok 0 warnings 0 errors", encoding="utf-8")

    covered = [f"translations/{t.name}" for t in wf.translation_paths]
    approve_checkpoint(
        wf.root,
        CheckpointType.QA_APPROVED,
        "reports/qa-report.yaml",
        covered,
    )
    return wf
