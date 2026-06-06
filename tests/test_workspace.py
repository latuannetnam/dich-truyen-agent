from pathlib import Path

from dich_truyen_agent.models import (
    BookMetadata,
    BookState,
    ChapterCatalog,
    ChapterState,
    OperationStatus,
    StageRecord,
    StageStatus,
    TranslationStyle,
)
from dich_truyen_agent.paths import temp_sibling_path, workspace_paths
from dich_truyen_agent.storage import atomic_write_yaml, load_yaml_model, sha256_file
from dich_truyen_agent.workspace import initialize_workspace, resume_workspace


def test_initialize_workspace_creates_documented_layout(
    books_root: Path,
    metadata: BookMetadata,
    catalog: ChapterCatalog,
    style: TranslationStyle,
) -> None:
    result = initialize_workspace(books_root, metadata, catalog, style)
    paths = workspace_paths(books_root, metadata.book_slug)

    assert result.status is OperationStatus.OK
    assert all(path.exists() for path in paths.stage_directories)
    assert all(path.exists() for path in (paths.book, paths.chapters, paths.state, paths.style))


def test_update_book_metadata(
    books_root: Path,
    metadata: BookMetadata,
    catalog: ChapterCatalog,
    style: TranslationStyle,
) -> None:
    workspace_root = initialized_workspace(books_root, metadata, catalog, style)
    from dich_truyen_agent.workspace import update_book_metadata
    
    result = update_book_metadata(
        workspace_root,
        translated_title="Tiêu đề đã dịch",
        translated_author="Tác giả đã dịch",
    )
    assert result.status is OperationStatus.OK
    
    paths = workspace_paths(books_root, metadata.book_slug)
    updated_meta = load_yaml_model(paths.book, BookMetadata)
    assert updated_meta.translated_title == "Tiêu đề đã dịch"
    assert updated_meta.translated_author == "Tác giả đã dịch"


def test_initialize_refuses_overwrite(
    books_root: Path,
    metadata: BookMetadata,
    catalog: ChapterCatalog,
    style: TranslationStyle,
) -> None:
    initialize_workspace(books_root, metadata, catalog, style)
    paths = workspace_paths(books_root, metadata.book_slug)
    before = paths.book.read_bytes()

    result = initialize_workspace(books_root, metadata, catalog, style)

    assert result.status is OperationStatus.BLOCKED
    assert paths.book.read_bytes() == before


def initialized_workspace(
    books_root: Path,
    metadata: BookMetadata,
    catalog: ChapterCatalog,
    style: TranslationStyle,
) -> Path:
    initialize_workspace(books_root, metadata, catalog, style)
    return workspace_paths(books_root, metadata.book_slug).root


def test_resume_reports_orphan_temp_without_promoting_it(
    books_root: Path,
    metadata: BookMetadata,
    catalog: ChapterCatalog,
    style: TranslationStyle,
) -> None:
    initialized_workspace(books_root, metadata, catalog, style)
    paths = workspace_paths(books_root, metadata.book_slug)
    orphan = temp_sibling_path(paths.state)
    orphan.write_text("partial", encoding="utf-8")

    result = resume_workspace(books_root, metadata.book_slug)

    assert result.status is OperationStatus.OK
    assert result.orphan_temp_paths == [str(orphan)]
    assert orphan.exists()


def test_resume_preserves_valid_completed_artifact(
    books_root: Path,
    metadata: BookMetadata,
    catalog: ChapterCatalog,
    style: TranslationStyle,
) -> None:
    initialized_workspace(books_root, metadata, catalog, style)
    paths = workspace_paths(books_root, metadata.book_slug)
    artifact = paths.raw / "0001-opening.txt"
    artifact.write_text("chapter text", encoding="utf-8")
    state = BookState(
        chapters=[
            ChapterState(
                chapter_id=1,
                raw=StageRecord(
                    status=StageStatus.COMPLETED,
                    canonical_path="raw/0001-opening.txt",
                    sha256=sha256_file(artifact),
                ),
            )
        ]
    )
    atomic_write_yaml(paths.state, state)
    before = artifact.read_bytes()

    result = resume_workspace(books_root, metadata.book_slug)

    assert result.status is OperationStatus.OK
    assert artifact.read_bytes() == before


def test_resume_blocks_missing_completed_artifact(
    books_root: Path,
    metadata: BookMetadata,
    catalog: ChapterCatalog,
    style: TranslationStyle,
) -> None:
    initialized_workspace(books_root, metadata, catalog, style)
    paths = workspace_paths(books_root, metadata.book_slug)
    atomic_write_yaml(
        paths.state,
        BookState(
            chapters=[
                ChapterState(
                    chapter_id=1,
                    raw=StageRecord(
                        status=StageStatus.COMPLETED,
                        canonical_path="raw/0001-opening.txt",
                        sha256="0" * 64,
                    ),
                )
            ]
        ),
    )

    result = resume_workspace(books_root, metadata.book_slug)

    assert result.status is OperationStatus.BLOCKED
    assert "missing" in result.reason


def test_resume_blocks_hash_mismatch(
    books_root: Path,
    metadata: BookMetadata,
    catalog: ChapterCatalog,
    style: TranslationStyle,
) -> None:
    initialized_workspace(books_root, metadata, catalog, style)
    paths = workspace_paths(books_root, metadata.book_slug)
    artifact = paths.raw / "0001-opening.txt"
    artifact.write_text("changed", encoding="utf-8")
    atomic_write_yaml(
        paths.state,
        BookState(
            chapters=[
                ChapterState(
                    chapter_id=1,
                    raw=StageRecord(
                        status=StageStatus.COMPLETED,
                        canonical_path="raw/0001-opening.txt",
                        sha256="0" * 64,
                    ),
                )
            ]
        ),
    )

    result = resume_workspace(books_root, metadata.book_slug)

    assert result.status is OperationStatus.BLOCKED
    assert "hash mismatch" in result.reason


def test_resume_blocks_state_chapter_missing_from_catalog(
    books_root: Path,
    metadata: BookMetadata,
    catalog: ChapterCatalog,
    style: TranslationStyle,
) -> None:
    initialized_workspace(books_root, metadata, catalog, style)
    paths = workspace_paths(books_root, metadata.book_slug)
    atomic_write_yaml(paths.state, BookState(chapters=[ChapterState(chapter_id=2)]))

    result = resume_workspace(books_root, metadata.book_slug)

    assert result.status is OperationStatus.BLOCKED
    assert "absent from catalog" in result.reason


def test_resume_blocks_catalog_chapter_missing_from_state(
    books_root: Path,
    metadata: BookMetadata,
    catalog: ChapterCatalog,
    style: TranslationStyle,
) -> None:
    initialized_workspace(books_root, metadata, catalog, style)
    paths = workspace_paths(books_root, metadata.book_slug)
    atomic_write_yaml(paths.state, BookState())

    result = resume_workspace(books_root, metadata.book_slug)

    assert result.status is OperationStatus.BLOCKED
    assert "absent from state" in result.reason


def test_workspace_yaml_is_validated_on_resume(
    books_root: Path,
    metadata: BookMetadata,
    catalog: ChapterCatalog,
    style: TranslationStyle,
) -> None:
    initialized_workspace(books_root, metadata, catalog, style)
    paths = workspace_paths(books_root, metadata.book_slug)
    paths.state.write_text("not: valid: yaml", encoding="utf-8")

    result = resume_workspace(books_root, metadata.book_slug)

    assert result.status is OperationStatus.BLOCKED
    assert "invalid workspace" in result.reason
    assert load_yaml_model(paths.book, BookMetadata) == metadata
