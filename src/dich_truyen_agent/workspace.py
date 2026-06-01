from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import yaml

from dich_truyen_agent.checkpoints import check_gate
from dich_truyen_agent.glossary import merge_glossary_proposals
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
    CheckpointType,
    StageRecord,
    GlossaryTerm,
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
    atomic_write_text,
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


def prepare_translation_context(workspace_root: Path, chapter_id: int) -> OperationResult:
    """Validate gates and return absolute context paths for the translation worker."""
    import json
    try:
        workspace_root = workspace_root.resolve()
        paths = workspace_paths(workspace_root.parent, workspace_root.name)
        
        # 1. Enforce crawl-approved checkpoint
        gate_res = check_gate(workspace_root, CheckpointType.CRAWL_APPROVED)
        if gate_res.status is not OperationStatus.OK:
            return gate_res
            
        catalog = load_yaml_model(paths.chapters, ChapterCatalog)
        state = load_yaml_model(paths.state, BookState)
        
        # 2. Check chapter exists in catalog
        catalog_by_id = {ch.chapter_id: ch for ch in catalog.chapters}
        if chapter_id not in catalog_by_id:
            return OperationResult(
                status=OperationStatus.ERROR,
                reason=f"chapter {chapter_id} not found in catalog",
            )
            
        entry = catalog_by_id[chapter_id]
        
        # 3. Enforce sequential ordering (TRAN-05)
        state_by_id = {ch.chapter_id: ch for ch in state.chapters}
        for ch in catalog.chapters:
            if ch.chapter_id < chapter_id:
                ch_state = state_by_id.get(ch.chapter_id)
                if not ch_state or ch_state.translation.status is not StageStatus.COMPLETED:
                    return OperationResult(
                        status=OperationStatus.BLOCKED,
                        reason=f"preceding chapter {ch.chapter_id} translation is not completed; sequential translation constraint violated",
                    )
                    
        # 4. Resolve raw path and other paths
        raw_path = paths.root / "raw" / entry.raw_filename
        if not raw_path.is_file():
            return OperationResult(
                status=OperationStatus.ERROR,
                reason=f"raw chapter file not found: {raw_path}",
            )
            
        # 5. Resolve predecessor translation context with fallback
        prev_translation_path = None
        is_fallback = True
        fallback_reason = "Chapter 1 has no predecessor context"
        
        if chapter_id > 1:
            prev_entry = catalog_by_id.get(chapter_id - 1)
            if prev_entry:
                candidate_path = paths.root / "translations" / prev_entry.translation_filename
                if candidate_path.is_file():
                    prev_translation_path = str(candidate_path.resolve())
                    is_fallback = False
                else:
                    fallback_reason = f"Predecessor chapter {chapter_id - 1} translation file is missing or reset"
                    
        context_payload = {
            "chapter_id": chapter_id,
            "title_cn": entry.original_title,
            "raw_path": str(raw_path.resolve()),
            "style_path": str(paths.style.resolve()),
            "glossary_path": str(paths.glossary.resolve()),
            "prev_translation_path": prev_translation_path,
            "is_fallback": is_fallback,
            "fallback_reason": fallback_reason if is_fallback else None,
        }
        
        return OperationResult(
            status=OperationStatus.OK,
            reason=json.dumps(context_payload, ensure_ascii=False),
            report_paths=[str(raw_path)],
        )
    except Exception as error:
        return OperationResult(
            status=OperationStatus.ERROR,
            reason=f"Failed to prepare translation context: {error}",
        )


def promote_chapter_translation(workspace_root: Path, chapter_id: int) -> OperationResult:
    """Validate staged translation outputs and atomically promote them, merging proposals and updating state."""
    try:
        workspace_root = workspace_root.resolve()
        paths = workspace_paths(workspace_root.parent, workspace_root.name)
        
        catalog = load_yaml_model(paths.chapters, ChapterCatalog)
        state = load_yaml_model(paths.state, BookState)
        
        catalog_by_id = {ch.chapter_id: ch for ch in catalog.chapters}
        state_by_id = {ch.chapter_id: ch for ch in state.chapters}
        
        if chapter_id not in catalog_by_id or chapter_id not in state_by_id:
            return OperationResult(
                status=OperationStatus.ERROR,
                reason=f"chapter {chapter_id} not found in catalog or state",
            )
            
        entry = catalog_by_id[chapter_id]
        chapter_state = state_by_id[chapter_id]
        
        staged_txt = paths.staging / f"chuong-{chapter_id:04d}-staged.txt"
        staged_yaml = paths.staging / f"chuong-{chapter_id:04d}-proposals.yaml"
        
        # 1. Validate staged translation existence and size
        if not staged_txt.is_file():
            return OperationResult(
                status=OperationStatus.ERROR,
                reason=f"staged translation file not found: {staged_txt}",
            )
            
        text = staged_txt.read_text(encoding="utf-8")
        if not text.strip() or len(text.strip()) < 10:
            return OperationResult(
                status=OperationStatus.ERROR,
                reason=f"staged translation file is empty or too short: {len(text)} characters",
            )
            
        # 2. Validate glossary proposals YAML if present
        proposals = {}
        if staged_yaml.is_file():
            try:
                with staged_yaml.open(encoding="utf-8") as stream:
                    proposals_raw = yaml.safe_load(stream)
                if proposals_raw and isinstance(proposals_raw, dict):
                    for term, data in proposals_raw.items():
                        if not isinstance(data, dict):
                            data = {}
                        proposals[term] = GlossaryTerm(
                            translation=data.get("translation", ""),
                            category=data.get("category", "other"),
                            source=f"chapter_{chapter_id}_proposal",
                            is_canonical=False,
                            note=data.get("note"),
                        )
            except Exception as e:
                return OperationResult(
                    status=OperationStatus.ERROR,
                    reason=f"invalid staged proposals YAML syntax: {e}",
                )
                
        # 3. Atomic Promotion of translation text
        rel_dest_path = f"translations/{entry.translation_filename}"
        dest_path = validate_workspace_relative_path(workspace_root, rel_dest_path)
        atomic_write_text(dest_path, text)
        
        # 4. SHA256 hashing and progressive glossary merge
        sha256 = sha256_file(dest_path)
        merge_report_paths = []
        if proposals:
            merge_res = merge_glossary_proposals(workspace_root, chapter_id, proposals)
            if merge_res.status is OperationStatus.ERROR:
                return merge_res
            merge_report_paths = merge_res.report_paths
            
        # 5. Update state.yaml translation status
        chapter_state.translation = StageRecord(
            status=StageStatus.COMPLETED,
            canonical_path=rel_dest_path,
            sha256=sha256,
            updated_at=datetime.now(UTC),
        )
        atomic_write_yaml(paths.state, state)
        
        # 6. Clean up staging files
        try:
            staged_txt.unlink()
        except OSError:
            pass
        if staged_yaml.is_file():
            try:
                staged_yaml.unlink()
            except OSError:
                pass
                
        return OperationResult(
            status=OperationStatus.OK,
            reason=f"chapter {chapter_id} translation promoted successfully",
            report_paths=[rel_dest_path] + merge_report_paths,
        )
    except Exception as error:
        return OperationResult(
            status=OperationStatus.ERROR,
            reason=f"Promotion failed: {error}",
        )


def get_next_pending_translation(workspace_root: Path) -> OperationResult:
    """Identify the next sequential pending translation chapter, validating queue integrity."""
    import json
    try:
        workspace_root = workspace_root.resolve()
        paths = workspace_paths(workspace_root.parent, workspace_root.name)
        
        catalog = load_yaml_model(paths.chapters, ChapterCatalog)
        state = load_yaml_model(paths.state, BookState)
        
        state_by_id = {ch.chapter_id: ch for ch in state.chapters}
        
        # Find first non-completed translation chapter
        target_ch = None
        for ch in catalog.chapters:
            ch_state = state_by_id.get(ch.chapter_id)
            if not ch_state or ch_state.translation.status is not StageStatus.COMPLETED:
                target_ch = ch
                break
                
        if not target_ch:
            comp = sum(1 for ch in state.chapters if ch.translation.status is StageStatus.COMPLETED)
            return OperationResult(
                status=OperationStatus.OK,
                reason="all chapter translations completed",
                progress=ProgressSummary(completed=comp, total=len(catalog.chapters)),
            )
            
        # Verify that all prior chapters are completed
        for ch in catalog.chapters:
            if ch.chapter_id < target_ch.chapter_id:
                ch_state = state_by_id.get(ch.chapter_id)
                if not ch_state or ch_state.translation.status is not StageStatus.COMPLETED:
                    return OperationResult(
                        status=OperationStatus.BLOCKED,
                        reason=f"preceding chapter {ch.chapter_id} translation is not completed; sequential translation constraint violated",
                        progress=ProgressSummary(
                            completed=sum(1 for x in state.chapters if x.translation.status is StageStatus.COMPLETED),
                            total=len(catalog.chapters),
                        ),
                    )
                    
        payload = {
            "chapter_id": target_ch.chapter_id,
            "slug": target_ch.slug,
            "original_title": target_ch.original_title,
        }
        
        comp = sum(1 for ch in state.chapters if ch.translation.status is StageStatus.COMPLETED)
        return OperationResult(
            status=OperationStatus.OK,
            reason=json.dumps(payload, ensure_ascii=False),
            progress=ProgressSummary(completed=comp, total=len(catalog.chapters)),
        )
    except Exception as error:
        return OperationResult(
            status=OperationStatus.ERROR,
            reason=f"Failed to identify next pending translation: {error}",
        )
