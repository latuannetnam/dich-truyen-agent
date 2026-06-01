import subprocess
from pathlib import Path

import pytest
import yaml

from dich_truyen_agent.checkpoints import approve_checkpoint
from dich_truyen_agent.models import (
    BookMetadata,
    BookState,
    ChapterCatalog,
    ChapterCatalogEntry,
    ChapterState,
    CheckpointType,
    OperationStatus,
    StageStatus,
    TranslationStyle,
)
from dich_truyen_agent.paths import workspace_paths
from dich_truyen_agent.storage import atomic_write_yaml, sha256_file
from dich_truyen_agent.workspace import initialize_workspace
from dich_truyen_agent.export import (
    compile_epub_in_memory,
    verify_epub_invariants,
    find_epubcheck,
    find_calibre,
    export_book,
)


@pytest.fixture
def export_workspace(
    books_root: Path,
    metadata: BookMetadata,
    style: TranslationStyle,
) -> Path:
    # Set up a catalog with 2 chapters
    catalog = ChapterCatalog(
        chapters=[
            ChapterCatalogEntry(
                chapter_id=1,
                slug="chuong-1",
                source_url="https://example.com/c1",
                original_title="Chuong 1",
                raw_filename="0001-c1.txt",
                translation_filename="0001-c1.txt",
            ),
            ChapterCatalogEntry(
                chapter_id=2,
                slug="chuong-2",
                source_url="https://example.com/c2",
                original_title="Chuong 2",
                raw_filename="0002-c2.txt",
                translation_filename="0002-c2.txt",
            ),
        ]
    )
    initialize_workspace(books_root, metadata, catalog, style)
    paths = workspace_paths(books_root, metadata.book_slug)

    # Populate raw and clean translated texts
    (paths.raw / "0001-c1.txt").write_text(
        "Hello Chinese novel world.", encoding="utf-8"
    )
    (paths.raw / "0002-c2.txt").write_text(
        "Another Chinese raw chapter.", encoding="utf-8"
    )

    (paths.translations / "0001-c1.txt").write_text(
        "Chương 1: Tiên Nhân Chỉ Lộ\nThế giới tiểu thuyết.", encoding="utf-8"
    )
    (paths.translations / "0002-c2.txt").write_text(
        "Chương 2: Luyện Khí Nhập Thể\nMột chương truyện thô khác.", encoding="utf-8"
    )

    # Update state to completed
    book_state = BookState(
        chapters=[
            ChapterState(
                chapter_id=1,
                translation={
                    "status": StageStatus.COMPLETED,
                    "canonical_path": "translations/0001-c1.txt",
                    "sha256": sha256_file(paths.translations / "0001-c1.txt"),
                },
            ),
            ChapterState(
                chapter_id=2,
                translation={
                    "status": StageStatus.COMPLETED,
                    "canonical_path": "translations/0002-c2.txt",
                    "sha256": sha256_file(paths.translations / "0002-c2.txt"),
                },
            ),
        ]
    )
    atomic_write_yaml(paths.state, book_state)
    return paths.root


def test_export_blocks_missing_qa_approved(export_workspace: Path) -> None:
    # 1. Initially, exporting blocks because there's no qa-approved checkpoint
    result = export_book(export_workspace, ["epub"])
    assert result.status is OperationStatus.BLOCKED
    assert "missing or stale QA approval checkpoint" in result.reason


def test_compile_epub_in_memory_and_invariants(export_workspace: Path) -> None:
    paths = workspace_paths(export_workspace.parent, export_workspace.name)
    book_metadata = load_yaml_model_helper(paths.book, BookMetadata)
    catalog = load_yaml_model_helper(paths.chapters, ChapterCatalog)

    epub_bytes = compile_epub_in_memory(export_workspace, book_metadata, catalog)
    assert len(epub_bytes) > 0

    # Verify invariants pass
    verify_epub_invariants(epub_bytes)

    # Test invalid invariants
    bad_bytes = epub_bytes[10:]  # Corrupted
    with pytest.raises(ValueError):
        verify_epub_invariants(bad_bytes)


def test_find_epubcheck(monkeypatch) -> None:
    # 1. Missing tool completely
    monkeypatch.delenv("DICH_TRUYEN_EPUBCHECK_PATH", raising=False)
    monkeypatch.setattr("shutil.which", lambda x: None)
    tool, is_jar = find_epubcheck()
    assert tool is None

    # 2. Configured as jar file
    temp_jar = Path("temp_epubcheck.jar")
    temp_jar.touch()
    monkeypatch.setenv("DICH_TRUYEN_EPUBCHECK_PATH", str(temp_jar.absolute()))
    tool, is_jar = find_epubcheck()
    assert tool == temp_jar.absolute()
    assert is_jar is True
    temp_jar.unlink()


def test_find_calibre(monkeypatch) -> None:
    # 1. Missing calibre completely
    monkeypatch.delenv("DICH_TRUYEN_CALIBRE_PATH", raising=False)
    monkeypatch.setattr("shutil.which", lambda x: None)
    monkeypatch.setattr(Path, "is_file", lambda self: False)
    tool = find_calibre()
    assert tool is None


def test_export_book_success_mocked(export_workspace: Path, monkeypatch) -> None:
    paths = workspace_paths(export_workspace.parent, export_workspace.name)

    # Approve QA checkpoint
    qa_report = paths.reports / "qa-report.yaml"
    qa_report.write_text("dummy qa report", encoding="utf-8")

    approve_checkpoint(
        export_workspace,
        CheckpointType.QA_APPROVED,
        "reports/qa-report.yaml",
        ["translations/0001-c1.txt", "translations/0002-c2.txt"],
    )

    # Mock find_epubcheck to return a dummy script and is_jar=False
    monkeypatch.setattr(
        "dich_truyen_agent.export.find_epubcheck", lambda: ("epubcheck", False)
    )

    # Mock subprocess.run for epubcheck and calibre
    called_cmds = []

    def mock_run(cmd, *args, **kwargs):
        called_cmds.append(cmd)

        class DummyCompletedProcess:
            returncode = 0
            stdout = "success"
            stderr = ""

        return DummyCompletedProcess()

    monkeypatch.setattr(subprocess, "run", mock_run)

    # Mock find_calibre to return a dummy binary path
    monkeypatch.setattr(
        "dich_truyen_agent.export.find_calibre", lambda: "ebook-convert"
    )

    # Run export
    res = export_book(export_workspace, ["epub", "azw3", "pdf"])
    assert res.status is OperationStatus.OK
    assert "export completed successfully" in res.reason.lower()

    # EPUB is created
    epub_file = paths.exports / f"{paths.root.name}.epub"
    assert epub_file.is_file()

    # Subprocesses are invoked
    assert len(called_cmds) >= 3  # epubcheck, calibre azw3, calibre pdf
    assert any("epubcheck" in str(c) for c in called_cmds)
    assert any("ebook-convert" in str(c) for c in called_cmds)


def load_yaml_model_helper(path: Path, model_type):
    with path.open(encoding="utf-8") as stream:
        data = yaml.safe_load(stream)
    return model_type.model_validate(data)
