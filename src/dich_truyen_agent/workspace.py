from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import yaml
from pydantic import BaseModel

from dich_truyen_agent.checkpoints import check_gate
from dich_truyen_agent.glossary import (
    prepare_glossary_merge,
    validate_staged_glossary_consistency,
    write_chapter_glossary_context,
)
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
    PromotionJournal,
    PromotionTargetWrite,
)
from dich_truyen_agent.paths import (
    WorkspacePaths,
    _is_beneath,
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


class PromotionFailpoint:
    _active_failpoint: str | None = None

    @classmethod
    def set(cls, name: str | None) -> None:
        cls._active_failpoint = name

    @classmethod
    def trigger(cls, name: str) -> None:
        if cls._active_failpoint == name:
            cls._active_failpoint = None
            raise RuntimeError(f"Simulation failpoint reached: {name}")


def _serialize_model(model: BaseModel) -> str:
    validated = type(model).model_validate(model.model_dump(mode="json"))
    return yaml.safe_dump(
        validated.model_dump(mode="json"),
        allow_unicode=True,
        sort_keys=False,
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


def update_book_metadata(
    workspace_root: Path,
    translated_title: str,
    translated_author: str | None = None,
) -> OperationResult:
    try:
        workspace_root = workspace_root.resolve()
        paths = workspace_paths(workspace_root.parent, workspace_root.name)
        
        metadata = load_yaml_model(paths.book, BookMetadata)
        metadata.translated_title = translated_title
        metadata.translated_author = translated_author
        
        atomic_write_yaml(paths.book, metadata)
        
        state = load_yaml_model(paths.state, BookState)
        return _ok("book metadata updated successfully", paths, state)
    except Exception as error:
        return OperationResult(
            status=OperationStatus.ERROR,
            reason=f"Failed to update book metadata: {error}",
        )


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


def get_staging_paths(
    paths: WorkspacePaths,
    chapter_id: int,
    *,
    run_id: str | None = None,
    attempt: int | None = None,
) -> tuple[Path, Path]:
    if run_id is not None:
        if attempt is None or attempt < 1:
            raise ValueError(f"attempt must be a positive integer, got: {attempt}")
        run_staging = paths.root / "reports" / "runs" / run_id / "staging"
        staged_txt = run_staging / f"chuong-{chapter_id:04d}-attempt-{attempt:02d}-staged.txt"
        staged_yaml = run_staging / f"chuong-{chapter_id:04d}-attempt-{attempt:02d}-proposals.yaml"
        return staged_txt, staged_yaml
    return (
        paths.staging / f"chuong-{chapter_id:04d}-staged.txt",
        paths.staging / f"chuong-{chapter_id:04d}-proposals.yaml",
    )


def prepare_translation_context(workspace_root: Path, chapter_id: int) -> OperationResult:
    """Validate gates and return absolute context paths for the translation worker."""
    import json
    try:
        workspace_root = Path(workspace_root).resolve()
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

        glossary_context_path = write_chapter_glossary_context(
            workspace_root,
            chapter_id,
            raw_path,
        )
            
        # 5. Resolve predecessor translation context strictly (no null fallback for chapter > 1)
        prev_translation_path = None
        is_fallback = False
        fallback_reason = None
        
        if chapter_id == 1:
            is_fallback = True
            fallback_reason = "Chapter 1 has no predecessor context"
        else:
            prev_entry = catalog_by_id.get(chapter_id - 1)
            if not prev_entry:
                return OperationResult(
                    status=OperationStatus.BLOCKED,
                    reason=f"predecessor chapter {chapter_id - 1} not found in catalog",
                )
            prev_state = state_by_id.get(chapter_id - 1)
            if not prev_state or prev_state.translation.status is not StageStatus.COMPLETED:
                return OperationResult(
                    status=OperationStatus.BLOCKED,
                    reason=f"preceding chapter {chapter_id - 1} translation is not completed; sequential translation constraint violated",
                )
            candidate_path = paths.root / "translations" / prev_entry.translation_filename
            if not candidate_path.is_file():
                return OperationResult(
                    status=OperationStatus.BLOCKED,
                    reason=f"predecessor chapter {chapter_id - 1} translation file is missing: {candidate_path}",
                )
            actual_sha = sha256_file(candidate_path)
            if actual_sha != prev_state.translation.sha256:
                return OperationResult(
                    status=OperationStatus.BLOCKED,
                    reason=f"hash mismatch for predecessor chapter {chapter_id - 1} translation file",
                )
            prev_translation_path = str(candidate_path.resolve())
                    
        context_payload = {
            "chapter_id": chapter_id,
            "title_cn": entry.original_title,
            "raw_path": str(raw_path.resolve()),
            "style_path": str(paths.style.resolve()),
            "glossary_path": str(paths.glossary.resolve()),
            "glossary_context_path": str(glossary_context_path.resolve()),
            "prev_translation_path": prev_translation_path,
            "is_fallback": is_fallback,
            "fallback_reason": fallback_reason,
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


def promote_chapter_translation(
    workspace_root: Path,
    chapter_id: int,
    *,
    run_id: str | None = None,
    attempt: int | None = None,
    staged_txt_path: Path | None = None,
    staged_yaml_path: Path | None = None,
) -> OperationResult:
    """Validate staged translation outputs and atomically promote them, merging proposals and updating state."""
    try:
        workspace_root = Path(workspace_root).resolve()
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
        
        if staged_txt_path is not None:
            staged_txt = Path(staged_txt_path)
            if not staged_txt.is_absolute():
                staged_txt = paths.root / staged_txt
            else:
                staged_txt = staged_txt.resolve()
                if not _is_beneath(paths.root, staged_txt):
                    return OperationResult(
                        status=OperationStatus.ERROR,
                        reason=f"staged translation path is outside canonical run staging: {staged_txt}",
                    )
            if run_id is not None:
                expected_dir = (paths.root / "reports" / "runs" / run_id / "staging").resolve()
                if staged_txt.parent.resolve() != expected_dir:
                    return OperationResult(
                        status=OperationStatus.ERROR,
                        reason=f"staged translation path is outside canonical run staging: {staged_txt}",
                    )
            if staged_yaml_path is not None:
                staged_yaml = Path(staged_yaml_path)
                if not staged_yaml.is_absolute():
                    staged_yaml = paths.root / staged_yaml
                else:
                    staged_yaml = staged_yaml.resolve()
            else:
                staged_yaml = staged_txt.with_name(staged_txt.name.replace("-staged.txt", "-proposals.yaml"))
        else:
            staged_txt, staged_yaml = get_staging_paths(paths, chapter_id, run_id=run_id, attempt=attempt)
        
        # 1. Validate staged translation existence and size
        if not staged_txt.is_file():
            return OperationResult(
                status=OperationStatus.ERROR,
                reason=f"staged translation file not found: {staged_txt}",
            )

        # Structural check for orchestrator / attempt-scoped promotion
        if run_id is not None or attempt is not None or staged_txt_path is not None:
            verification = verify_staged_chapter(
                workspace_root,
                chapter_id,
                run_id=run_id,
                attempt=attempt,
                staged_txt_path=staged_txt,
            )
            if verification.status is not OperationStatus.OK:
                return verification
            
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

        raw_path = paths.raw / entry.raw_filename
        glossary_validation = validate_staged_glossary_consistency(
            workspace_root,
            chapter_id,
            proposals,
            text,
            raw_path,
        )
        if glossary_validation.status is not OperationStatus.OK:
            return glossary_validation
                
        # 3. Prepare all replacement payloads and hashes before the first write
        rel_dest_path = f"translations/{entry.translation_filename}"
        dest_path = validate_workspace_relative_path(workspace_root, rel_dest_path)
        dest_before_sha = sha256_file(dest_path) if dest_path.is_file() else None
        dest_after_sha = hashlib.sha256(text.encode("utf-8")).hexdigest()

        targets: list[PromotionTargetWrite] = [
            PromotionTargetWrite(
                path=rel_dest_path,
                before_sha256=dest_before_sha,
                after_sha256=dest_after_sha,
                content=text,
            )
        ]

        merge_report_paths: list[str] = []
        if proposals:
            snapshot_filename = f"chapter-{chapter_id:04d}.yaml"
            snapshot_path = paths.glossary_snapshots / snapshot_filename
            existing_glossary = (
                load_yaml_model(paths.glossary, BookGlossary)
                if paths.glossary.is_file()
                else BookGlossary(terms={})
            )
            snapshot_content = _serialize_model(existing_glossary)
            snapshot_before = sha256_file(snapshot_path) if snapshot_path.is_file() else None
            snapshot_after = hashlib.sha256(snapshot_content.encode("utf-8")).hexdigest()
            targets.append(
                PromotionTargetWrite(
                    path=f"checkpoints/glossary-snapshots/{snapshot_filename}",
                    before_sha256=snapshot_before,
                    after_sha256=snapshot_after,
                    content=snapshot_content,
                )
            )

            merged_glossary, conflict_report = prepare_glossary_merge(
                workspace_root, chapter_id, proposals
            )
            glossary_content = _serialize_model(merged_glossary)
            glossary_before = sha256_file(paths.glossary) if paths.glossary.is_file() else None
            glossary_after = hashlib.sha256(glossary_content.encode("utf-8")).hexdigest()
            targets.append(
                PromotionTargetWrite(
                    path="glossary.yaml",
                    before_sha256=glossary_before,
                    after_sha256=glossary_after,
                    content=glossary_content,
                )
            )

            if conflict_report is not None and conflict_report.conflicts:
                conflicts_content = _serialize_model(conflict_report)
                conflicts_before = (
                    sha256_file(paths.glossary_conflicts)
                    if paths.glossary_conflicts.is_file()
                    else None
                )
                conflicts_after = hashlib.sha256(conflicts_content.encode("utf-8")).hexdigest()
                targets.append(
                    PromotionTargetWrite(
                        path="reports/glossary-conflicts.yaml",
                        before_sha256=conflicts_before,
                        after_sha256=conflicts_after,
                        content=conflicts_content,
                    )
                )
                merge_report_paths.append("reports/glossary-conflicts.yaml")

        # Prepare updated state
        updated_state = state.model_copy(deep=True)
        for ch in updated_state.chapters:
            if ch.chapter_id == chapter_id:
                ch.translation = StageRecord(
                    status=StageStatus.COMPLETED,
                    canonical_path=rel_dest_path,
                    sha256=dest_after_sha,
                    updated_at=datetime.now(UTC),
                )
                break
        state_content = _serialize_model(updated_state)
        state_before = sha256_file(paths.state) if paths.state.is_file() else None
        state_after = hashlib.sha256(state_content.encode("utf-8")).hexdigest()
        targets.append(
            PromotionTargetWrite(
                path="state.yaml",
                before_sha256=state_before,
                after_sha256=state_after,
                content=state_content,
            )
        )

        # 4. Atomically persist journal
        journal = PromotionJournal(
            chapter_id=chapter_id,
            run_id=run_id,
            attempt=attempt,
            targets=targets,
            staged_txt_path=str(staged_txt.resolve()) if staged_txt.is_file() else None,
            staged_yaml_path=str(staged_yaml.resolve()) if staged_yaml.is_file() else None,
        )
        journal_path = paths.reports / f"promotion-journal-{chapter_id}.yaml"
        atomic_write_yaml(journal_path, journal)

        # 5. Atomically replace each target with failpoints
        # Target 1: canonical text
        atomic_write_text(dest_path, text)
        PromotionFailpoint.trigger("after_canonical")

        # Target 2..N-1: glossary snapshot, glossary, conflicts
        if proposals:
            for t in targets[1:-1]:
                t_path = validate_workspace_relative_path(workspace_root, t.path)
                atomic_write_text(t_path, t.content)
            PromotionFailpoint.trigger("after_glossary")

        # Target N: state
        atomic_write_text(paths.state, targets[-1].content)
        PromotionFailpoint.trigger("after_state")

        # 6. Verify all targets
        for t in targets:
            t_path = validate_workspace_relative_path(workspace_root, t.path)
            if not t_path.is_file() or sha256_file(t_path) != t.after_sha256:
                raise RuntimeError(f"Post-promotion verification failed for {t.path}")

        # 7. Cleanup staging files and remove journal
        try:
            journal_path.unlink()
        except OSError:
            pass

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


def recover_chapter_promotion(workspace_root: Path, chapter_id: int) -> OperationResult:
    """Recover an interrupted chapter promotion using the durable promotion journal."""
    try:
        workspace_root = Path(workspace_root).resolve()
        paths = workspace_paths(workspace_root.parent, workspace_root.name)
        journal_path = paths.reports / f"promotion-journal-{chapter_id}.yaml"
        if not journal_path.is_file():
            if paths.state.is_file():
                state = load_yaml_model(paths.state, BookState)
                for ch in state.chapters:
                    if ch.chapter_id == chapter_id and ch.translation.status is StageStatus.COMPLETED:
                        return OperationResult(
                            status=OperationStatus.OK,
                            reason=f"chapter {chapter_id} promotion already completed (no active journal)",
                        )
            return OperationResult(
                status=OperationStatus.OK,
                reason=f"no promotion journal found for chapter {chapter_id}",
            )

        journal = load_yaml_model(journal_path, PromotionJournal)

        # 1. Inspect all targets for divergence
        for target in journal.targets:
            target_path = validate_workspace_relative_path(workspace_root, target.path)
            current_sha = sha256_file(target_path) if target_path.is_file() else None
            if current_sha != target.after_sha256 and current_sha != target.before_sha256:
                return OperationResult(
                    status=OperationStatus.BLOCKED,
                    reason=(
                        f"Target file {target.path} diverged during recovery: "
                        f"current SHA256 {current_sha} matches neither recorded before ({target.before_sha256}) "
                        f"nor after ({target.after_sha256})"
                    ),
                )

        # 2. Roll forward all targets not yet at after_sha256
        for target in journal.targets:
            target_path = validate_workspace_relative_path(workspace_root, target.path)
            current_sha = sha256_file(target_path) if target_path.is_file() else None
            if current_sha != target.after_sha256:
                atomic_write_text(target_path, target.content)

        # 3. Verify all targets
        for target in journal.targets:
            target_path = validate_workspace_relative_path(workspace_root, target.path)
            current_sha = sha256_file(target_path) if target_path.is_file() else None
            if current_sha != target.after_sha256:
                return OperationResult(
                    status=OperationStatus.ERROR,
                    reason=f"Verification failed after recovery write for {target.path}",
                )

        # 4. Clean up staging files if recorded
        if journal.staged_txt_path:
            p = Path(journal.staged_txt_path)
            if p.is_file():
                try:
                    p.unlink()
                except OSError:
                    pass
        if journal.staged_yaml_path:
            p = Path(journal.staged_yaml_path)
            if p.is_file():
                try:
                    p.unlink()
                except OSError:
                    pass

        # 5. Remove journal
        try:
            journal_path.unlink()
        except OSError:
            pass

        return OperationResult(
            status=OperationStatus.OK,
            reason=f"chapter {chapter_id} promotion recovered successfully",
        )
    except Exception as error:
        return OperationResult(
            status=OperationStatus.ERROR,
            reason=f"Recovery failed: {error}",
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


def next_translation_work_item(
    workspace_root: Path,
    *,
    run_id: str | None = None,
    attempt: int | None = None,
) -> OperationResult:
    """Return a compact, deterministic payload for the next translation task."""
    try:
        workspace_root = Path(workspace_root).resolve()
        paths = workspace_paths(workspace_root.parent, workspace_root.name)

        catalog = load_yaml_model(paths.chapters, ChapterCatalog)
        state = load_yaml_model(paths.state, BookState)
        state_by_id = {chapter.chapter_id: chapter for chapter in state.chapters}
        completed = sum(
            1
            for chapter in state.chapters
            if chapter.translation.status is StageStatus.COMPLETED
        )
        total = len(catalog.chapters)

        gate_res = check_gate(workspace_root, CheckpointType.CRAWL_APPROVED)
        if gate_res.status is not OperationStatus.OK:
            return OperationResult(
                status=gate_res.status,
                reason=gate_res.reason,
                progress=ProgressSummary(completed=completed, total=total),
                approval_path=gate_res.approval_path,
                report_paths=gate_res.report_paths,
                data={
                    "state": "blocked",
                    "progress_completed": completed,
                    "progress_total": total,
                    "next_chapter_id": None,
                    "failure_reason": gate_res.reason,
                },
            )

        target = None
        for chapter in catalog.chapters:
            ch_state = state_by_id.get(chapter.chapter_id)
            if not ch_state or ch_state.translation.status is not StageStatus.COMPLETED:
                target = chapter
                break

        if target is None:
            return OperationResult(
                status=OperationStatus.OK,
                reason="all chapter translations completed",
                progress=ProgressSummary(completed=completed, total=total),
                data={
                    "state": "completed",
                    "progress_completed": completed,
                    "progress_total": total,
                    "next_chapter_id": None,
                    "message": "all chapter translations completed",
                },
            )

        completed_after_pending = [
            chapter.chapter_id
            for chapter in catalog.chapters
            if chapter.chapter_id > target.chapter_id
            and (
                state_by_id.get(chapter.chapter_id)
                and state_by_id[chapter.chapter_id].translation.status
                is StageStatus.COMPLETED
            )
        ]
        if completed_after_pending:
            reason = (
                "translation state gap: completed chapter(s) "
                f"{completed_after_pending} appear after pending chapter {target.chapter_id}"
            )
            return OperationResult(
                status=OperationStatus.BLOCKED,
                reason=reason,
                progress=ProgressSummary(
                    completed=completed,
                    total=total,
                    current_chapter_id=target.chapter_id,
                ),
                data={
                    "state": "blocked",
                    "chapter_id": target.chapter_id,
                    "progress_completed": completed,
                    "progress_total": total,
                    "completed_after_pending": completed_after_pending,
                    "failure_reason": reason,
                },
            )

        context = prepare_translation_context(workspace_root, target.chapter_id)
        if context.status is not OperationStatus.OK:
            state_name = (
                "blocked"
                if context.status is OperationStatus.BLOCKED
                else "error"
            )
            return OperationResult(
                status=context.status,
                reason=context.reason,
                progress=ProgressSummary(
                    completed=completed,
                    total=total,
                    current_chapter_id=target.chapter_id,
                ),
                report_paths=context.report_paths,
                approval_path=context.approval_path,
                data={
                    "state": state_name,
                    "chapter_id": target.chapter_id,
                    "progress_completed": completed,
                    "progress_total": total,
                    "failure_reason": context.reason,
                },
            )

        context_payload = json.loads(context.reason)
        staged_txt, staged_yaml = get_staging_paths(
            paths, target.chapter_id, run_id=run_id, attempt=attempt
        )
        payload = {
            "state": "pending",
            "chapter_id": target.chapter_id,
            "slug": target.slug,
            "original_title": target.original_title,
            "progress_completed": completed,
            "progress_total": total,
            "raw_path": context_payload["raw_path"],
            "style_path": context_payload["style_path"],
            "glossary_path": context_payload["glossary_path"],
            "glossary_context_path": context_payload["glossary_context_path"],
            "prev_translation_path": context_payload["prev_translation_path"],
            "staged_txt": str(staged_txt.resolve()),
            "staged_yaml": str(staged_yaml.resolve()),
            "is_fallback": context_payload["is_fallback"],
            "fallback_reason": context_payload["fallback_reason"],
            "staged_txt_exists": staged_txt.is_file(),
            "staged_yaml_exists": staged_yaml.is_file(),
        }
        if run_id is not None:
            payload["run_id"] = run_id
        if attempt is not None:
            payload["attempt"] = attempt
        return OperationResult(
            status=OperationStatus.OK,
            reason=f"translation work item ready for chapter {target.chapter_id}",
            progress=ProgressSummary(
                completed=completed,
                total=total,
                current_chapter_id=target.chapter_id,
            ),
            data=payload,
        )
    except Exception as error:
        return OperationResult(
            status=OperationStatus.ERROR,
            reason=f"Failed to prepare next translation work item: {error}",
            data={
                "state": "error",
                "failure_reason": f"Failed to prepare next translation work item: {error}",
            },
        )


def verify_staged_chapter(
    workspace_root: Path,
    chapter_id: int,
    *,
    run_id: str | None = None,
    attempt: int | None = None,
    staged_txt_path: Path | None = None,
) -> OperationResult:
    """Perform structural staged-output checks without replacing promotion gates."""
    try:
        workspace_root = Path(workspace_root).resolve()
        paths = workspace_paths(workspace_root.parent, workspace_root.name)

        if staged_txt_path is not None:
            staged_txt = Path(staged_txt_path)
            if not staged_txt.is_absolute():
                staged_txt = paths.root / staged_txt
            else:
                staged_txt = staged_txt.resolve()
                if not _is_beneath(paths.root, staged_txt):
                    reason = f"staged translation path escapes workspace: {staged_txt}"
                    return OperationResult(
                        status=OperationStatus.ERROR,
                        reason=reason,
                        data={"ok": False, "chapter_id": chapter_id, "first_line": None, "reason": reason},
                    )
            if run_id is not None:
                expected_dir = (paths.root / "reports" / "runs" / run_id / "staging").resolve()
                if staged_txt.parent.resolve() != expected_dir:
                    reason = f"staged translation path {staged_txt} is outside canonical run staging {expected_dir}"
                    return OperationResult(
                        status=OperationStatus.ERROR,
                        reason=reason,
                        data={"ok": False, "chapter_id": chapter_id, "first_line": None, "reason": reason},
                    )
                if attempt is not None:
                    expected_name = f"chuong-{chapter_id:04d}-attempt-{attempt:02d}-staged.txt"
                    if staged_txt.name != expected_name:
                        reason = f"staged translation filename {staged_txt.name} does not match expected {expected_name}"
                        return OperationResult(
                            status=OperationStatus.ERROR,
                            reason=reason,
                            data={"ok": False, "chapter_id": chapter_id, "first_line": None, "reason": reason},
                        )
        else:
            staged_txt, _ = get_staging_paths(paths, chapter_id, run_id=run_id, attempt=attempt)

        if not staged_txt.is_file() or not staged_txt.read_text(encoding="utf-8").strip():
            reason = f"staged translation missing or empty: {staged_txt}"
            return OperationResult(
                status=OperationStatus.ERROR,
                reason=reason,
                data={
                    "ok": False,
                    "chapter_id": chapter_id,
                    "first_line": None,
                    "reason": reason,
                },
            )

        text = staged_txt.read_text(encoding="utf-8")
        lines = text.splitlines()
        first_line = lines[0] if lines else ""
        accepted_prefixes = (f"# Chương {chapter_id}", f"# Chuong {chapter_id}")
        if not first_line.startswith(accepted_prefixes):
            reason = f"line 1 must start with '# Chương {chapter_id}'"
            return OperationResult(
                status=OperationStatus.ERROR,
                reason=reason,
                data={
                    "ok": False,
                    "chapter_id": chapter_id,
                    "first_line": first_line,
                    "reason": reason,
                },
            )
        if len(lines) < 2 or lines[1] != "":
            reason = "line 2 must be blank"
            return OperationResult(
                status=OperationStatus.ERROR,
                reason=reason,
                data={
                    "ok": False,
                    "chapter_id": chapter_id,
                    "first_line": first_line,
                    "reason": reason,
                },
            )

        return OperationResult(
            status=OperationStatus.OK,
            reason=f"staged chapter {chapter_id} structure verified",
            data={
                "ok": True,
                "chapter_id": chapter_id,
                "first_line": first_line,
                "character_count": len(text),
                "reason": None,
            },
        )
    except Exception as error:
        reason = f"Failed to verify staged chapter: {error}"
        return OperationResult(
            status=OperationStatus.ERROR,
            reason=reason,
            data={
                "ok": False,
                "chapter_id": chapter_id,
                "first_line": None,
                "reason": reason,
            },
        )
