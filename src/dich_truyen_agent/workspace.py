from __future__ import annotations

from pathlib import Path

import yaml

from dich_truyen_agent.models import (
    BookMetadata,
    BookState,
    ChapterCatalog,
    ChapterState,
    OperationResult,
    OperationStatus,
    ProgressSummary,
    StageStatus,
    TranslationStyle,
    BookGlossary,
    GlossaryConflictReport,
)
from dich_truyen_agent.paths import (
    WorkspacePaths,
    validate_workspace_relative_path,
    workspace_paths,
)
from dich_truyen_agent.storage import (
    atomic_write_yaml,
    find_orphan_temp_files,
    load_yaml_model,
    sha256_file,
)


def _compact_paths(paths: list[Path]) -> list[str]:
    return [str(path) for path in paths]


def _ok(reason: str, paths: WorkspacePaths, state: BookState) -> OperationResult:
    completed = sum(
        stage.status is StageStatus.COMPLETED
        for chapter in state.chapters
        for stage in (chapter.raw, chapter.translation)
    )
    return OperationResult(
        status=OperationStatus.OK,
        reason=reason,
        progress=ProgressSummary(completed=completed, total=len(state.chapters) * 2),
        orphan_temp_paths=_compact_paths(find_orphan_temp_files(paths.root)),
    )


def initialize_workspace(
    books_root: Path,
    metadata: BookMetadata,
    catalog: ChapterCatalog,
    style: TranslationStyle,
    resume: bool = False,
) -> OperationResult:
    paths = workspace_paths(books_root, metadata.book_slug)
    if paths.root.exists():
        if resume:
            return resume_workspace(books_root, metadata.book_slug)
        return OperationResult(
            status=OperationStatus.BLOCKED,
            reason=f"workspace already exists; use explicit resume: {paths.root}",
        )

    paths.root.mkdir(parents=True)
    for directory in paths.stage_directories:
        directory.mkdir(parents=True, exist_ok=True)
    state = BookState(
        chapters=[ChapterState(chapter_id=chapter.chapter_id) for chapter in catalog.chapters]
    )
    atomic_write_yaml(paths.book, metadata)
    atomic_write_yaml(paths.chapters, catalog)
    atomic_write_yaml(paths.state, state)
    atomic_write_yaml(paths.style, style)
    return _ok("workspace initialized", paths, state)


def validate_catalog_state(catalog: ChapterCatalog, state: BookState) -> None:
    catalog_ids = {chapter.chapter_id for chapter in catalog.chapters}
    state_ids = {chapter.chapter_id for chapter in state.chapters}
    for chapter in state.chapters:
        if chapter.chapter_id not in catalog_ids:
            raise ValueError(f"state chapter {chapter.chapter_id} is absent from catalog")
    missing_state_ids = catalog_ids - state_ids
    if missing_state_ids:
        missing = ", ".join(str(chapter_id) for chapter_id in sorted(missing_state_ids))
        raise ValueError(f"catalog chapters absent from state: {missing}")


def _validate_completed_artifacts(
    paths: WorkspacePaths, catalog: ChapterCatalog, state: BookState
) -> None:
    catalog_by_id = {chapter.chapter_id: chapter for chapter in catalog.chapters}
    for chapter in state.chapters:
        for stage_name, stage in (("raw", chapter.raw), ("translation", chapter.translation)):
            if stage.status is not StageStatus.COMPLETED:
                continue
            catalog_entry = catalog_by_id[chapter.chapter_id]
            filename = (
                catalog_entry.raw_filename
                if stage_name == "raw"
                else catalog_entry.translation_filename
            )
            expected_path = f"{stage_name if stage_name == 'raw' else 'translations'}/{filename}"
            if stage.canonical_path != expected_path:
                raise ValueError(
                    f"completed {stage_name} artifact path for chapter {chapter.chapter_id} "
                    f"must match catalog: {expected_path}"
                )
            artifact = validate_workspace_relative_path(paths.root, stage.canonical_path or "")
            if not artifact.is_file():
                raise ValueError(
                    f"missing completed {stage_name} artifact for chapter {chapter.chapter_id}: "
                    f"{artifact}; repair or reset required"
                )
            try:
                digest = sha256_file(artifact)
            except OSError as error:
                raise ValueError(
                    f"unreadable completed {stage_name} artifact for chapter "
                    f"{chapter.chapter_id}: {artifact}; repair or reset required"
                ) from error
            if digest != stage.sha256:
                raise ValueError(
                    f"hash mismatch for completed {stage_name} artifact for chapter "
                    f"{chapter.chapter_id}: {artifact}; repair or reset required"
                )


def inspect_workspace(workspace_root: Path) -> OperationResult:
    paths = workspace_paths(workspace_root.parent, workspace_root.name)
    try:
        load_yaml_model(paths.book, BookMetadata)
        catalog = load_yaml_model(paths.chapters, ChapterCatalog)
        state = load_yaml_model(paths.state, BookState)
        load_yaml_model(paths.style, TranslationStyle)
        validate_catalog_state(catalog, state)
        _validate_completed_artifacts(paths, catalog, state)
        if paths.glossary.exists():
            load_yaml_model(paths.glossary, BookGlossary)
        if paths.glossary_conflicts.exists():
            load_yaml_model(paths.glossary_conflicts, GlossaryConflictReport)
    except (OSError, ValueError, yaml.YAMLError) as error:
        return OperationResult(
            status=OperationStatus.BLOCKED,
            reason=f"invalid workspace: {error}",
            orphan_temp_paths=_compact_paths(find_orphan_temp_files(paths.root)),
        )
    return _ok("workspace is valid", paths, state)


def resume_workspace(books_root: Path, book_slug: str) -> OperationResult:
    paths = workspace_paths(books_root, book_slug)
    if not paths.root.is_dir():
        return OperationResult(
            status=OperationStatus.BLOCKED,
            reason=f"workspace does not exist: {paths.root}",
        )
    return inspect_workspace(paths.root)


def install_discovered_catalog(
    workspace_root: Path,
    catalog: ChapterCatalog,
) -> None:
    paths = workspace_paths(workspace_root.parent, workspace_root.name)
    if not paths.chapters.exists():
        atomic_write_yaml(paths.chapters, catalog)
    if not paths.state.exists():
        state = BookState(
            chapters=[ChapterState(chapter_id=chapter.chapter_id) for chapter in catalog.chapters]
        )
        atomic_write_yaml(paths.state, state)
