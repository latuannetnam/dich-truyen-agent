from __future__ import annotations

import logging
from pathlib import Path

from dich_truyen_agent.models import (
    BookGlossary,
    GlossaryTerm,
    GlossaryContext,
    GlossaryContextTerm,
    GlossaryConflict,
    GlossaryConflictReport,
    OperationResult,
    OperationStatus,
)
from dich_truyen_agent.paths import workspace_paths
from dich_truyen_agent.storage import atomic_write_yaml, load_yaml_model

logger = logging.getLogger(__name__)


def _load_glossary(paths) -> BookGlossary:
    if paths.glossary.is_file():
        return load_yaml_model(paths.glossary, BookGlossary)
    return BookGlossary(terms={})


def _load_conflict_report(paths) -> GlossaryConflictReport:
    if paths.glossary_conflicts.is_file():
        return load_yaml_model(paths.glossary_conflicts, GlossaryConflictReport)
    return GlossaryConflictReport(conflicts=[])


def _dedupe_preserving_order(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _rejected_aliases_by_term(
    glossary: BookGlossary,
    conflict_report: GlossaryConflictReport,
) -> dict[str, list[str]]:
    aliases: dict[str, list[str]] = {}
    for conflict in conflict_report.conflicts:
        current_term = glossary.terms.get(conflict.term)
        expected_translation = (
            current_term.translation if current_term else conflict.existing_translation
        )
        if conflict.proposed_translation == expected_translation:
            continue
        aliases.setdefault(conflict.term, []).append(conflict.proposed_translation)
    return {
        term: _dedupe_preserving_order(term_aliases)
        for term, term_aliases in aliases.items()
    }


def glossary_context_path(workspace_root: Path, chapter_id: int) -> Path:
    paths = workspace_paths(workspace_root.parent, workspace_root.name)
    return paths.staging / f"chuong-{chapter_id:04d}-glossary-context.yaml"


def build_chapter_glossary_context(
    workspace_root: Path,
    chapter_id: int,
    raw_text: str,
) -> GlossaryContext:
    paths = workspace_paths(workspace_root.parent, workspace_root.name)
    glossary = _load_glossary(paths)
    conflict_report = _load_conflict_report(paths)
    aliases = _rejected_aliases_by_term(glossary, conflict_report)

    relevant_terms = {}
    for term, glossary_term in glossary.terms.items():
        if term not in raw_text:
            continue
        relevant_terms[term] = GlossaryContextTerm(
            translation=glossary_term.translation,
            category=glossary_term.category,
            source=glossary_term.source,
            is_canonical=glossary_term.is_canonical,
            note=glossary_term.note,
            rejected_aliases=aliases.get(term, []),
        )

    return GlossaryContext(chapter_id=chapter_id, terms=relevant_terms)


def write_chapter_glossary_context(
    workspace_root: Path,
    chapter_id: int,
    raw_path: Path,
) -> Path:
    raw_text = raw_path.read_text(encoding="utf-8")
    context = build_chapter_glossary_context(workspace_root, chapter_id, raw_text)
    context_path = glossary_context_path(workspace_root, chapter_id)
    atomic_write_yaml(context_path, context)
    return context_path


def append_glossary_conflicts(
    workspace_root: Path,
    conflicts: list[GlossaryConflict],
) -> None:
    if not conflicts:
        return

    paths = workspace_paths(workspace_root.parent, workspace_root.name)
    conflict_report = _load_conflict_report(paths)
    existing_keys = {
        (
            conflict.term,
            conflict.existing_translation,
            conflict.proposed_translation,
            conflict.proposed_source,
            conflict.chapter_id,
        )
        for conflict in conflict_report.conflicts
    }
    for conflict in conflicts:
        key = (
            conflict.term,
            conflict.existing_translation,
            conflict.proposed_translation,
            conflict.proposed_source,
            conflict.chapter_id,
        )
        if key in existing_keys:
            continue
        conflict_report.conflicts.append(conflict)
        existing_keys.add(key)

    atomic_write_yaml(paths.glossary_conflicts, conflict_report)


def find_proposal_conflicts(
    workspace_root: Path,
    chapter_id: int,
    proposals: dict[str, GlossaryTerm],
) -> list[GlossaryConflict]:
    paths = workspace_paths(workspace_root.parent, workspace_root.name)
    glossary = _load_glossary(paths)
    conflicts = []
    for term, proposed_term in proposals.items():
        existing_term = glossary.terms.get(term)
        if existing_term is None or existing_term.translation == proposed_term.translation:
            continue
        conflicts.append(
            GlossaryConflict(
                term=term,
                existing_translation=existing_term.translation,
                existing_source=existing_term.source,
                proposed_translation=proposed_term.translation,
                proposed_source=f"chapter_{chapter_id}_proposal",
                chapter_id=chapter_id,
            )
        )
    return conflicts


def find_rejected_alias_usages(
    context: GlossaryContext,
    text: str,
) -> list[dict[str, str]]:
    usages = []
    for term, context_term in context.terms.items():
        for alias in context_term.rejected_aliases:
            if alias == context_term.translation or alias not in text:
                continue
            usages.append(
                {
                    "term": term,
                    "expected_translation": context_term.translation,
                    "rejected_alias": alias,
                }
            )
    return usages


def validate_staged_glossary_consistency(
    workspace_root: Path,
    chapter_id: int,
    proposals: dict[str, GlossaryTerm],
    staged_text: str,
    raw_path: Path,
) -> OperationResult:
    paths = workspace_paths(workspace_root.parent, workspace_root.name)
    proposal_conflicts = find_proposal_conflicts(workspace_root, chapter_id, proposals)
    if proposal_conflicts:
        append_glossary_conflicts(workspace_root, proposal_conflicts)
        first = proposal_conflicts[0]
        return OperationResult(
            status=OperationStatus.BLOCKED,
            reason=(
                "glossary consistency blocked: proposal for "
                f"'{first.term}' uses '{first.proposed_translation}', but glossary "
                f"requires '{first.existing_translation}'"
            ),
            report_paths=[str(paths.glossary_conflicts)],
        )

    context_path = glossary_context_path(workspace_root, chapter_id)
    if context_path.is_file():
        context = load_yaml_model(context_path, GlossaryContext)
    else:
        context = build_chapter_glossary_context(
            workspace_root,
            chapter_id,
            raw_path.read_text(encoding="utf-8"),
        )
        atomic_write_yaml(context_path, context)

    alias_usages = find_rejected_alias_usages(context, staged_text)
    if alias_usages:
        first = alias_usages[0]
        return OperationResult(
            status=OperationStatus.BLOCKED,
            reason=(
                "glossary consistency blocked: rejected glossary alias "
                f"'{first['rejected_alias']}' used for '{first['term']}', expected "
                f"'{first['expected_translation']}'"
            ),
            report_paths=[str(context_path)],
        )

    return OperationResult(
        status=OperationStatus.OK,
        reason="staged glossary consistency validated",
    )


def initialize_glossary_file(workspace_root: Path, terms: dict[str, dict]) -> OperationResult:
    """Validate and write the BookGlossary to glossary.yaml atomically."""
    try:
        paths = workspace_paths(workspace_root.parent, workspace_root.name)
        
        glossary_terms = {}
        for term, data in terms.items():
            glossary_term = GlossaryTerm(
                translation=data.get("translation", ""),
                category=data.get("category", "other"),
                source="initial_generation",
                is_canonical=False,
                note=data.get("note"),
            )
            glossary_terms[term] = glossary_term
            
        glossary = BookGlossary(terms=glossary_terms)
        atomic_write_yaml(paths.glossary, glossary)
        
        return OperationResult(
            status=OperationStatus.OK,
            reason="Glossary initialized successfully",
            report_paths=[str(paths.glossary)],
        )
    except Exception as error:
        logger.exception("Failed to initialize glossary file")
        return OperationResult(
            status=OperationStatus.ERROR,
            reason=f"Failed to initialize glossary: {error}",
        )


def merge_glossary_proposals(
    workspace_root: Path,
    chapter_id: int,
    proposals: dict[str, GlossaryTerm],
) -> OperationResult:
    """Merge chapter proposals into glossary.yaml, creating snapshots and logging conflicts."""
    try:
        paths = workspace_paths(workspace_root.parent, workspace_root.name)
        
        # 1. Load existing BookGlossary or initialize a new one
        if paths.glossary.is_file():
            glossary = load_yaml_model(paths.glossary, BookGlossary)
        else:
            glossary = BookGlossary(terms={})
            
        # 2. Automatically create snapshot backup prior to merge
        snapshot_filename = f"chapter-{chapter_id:04d}.yaml"
        snapshot_path = paths.glossary_snapshots / snapshot_filename
        atomic_write_yaml(snapshot_path, glossary)
        
        # 3. Load or initialize GlossaryConflictReport
        if paths.glossary_conflicts.is_file():
            conflict_report = load_yaml_model(paths.glossary_conflicts, GlossaryConflictReport)
        else:
            conflict_report = GlossaryConflictReport(conflicts=[])
            
        # 4. Process proposals
        new_terms_count = 0
        conflicts_count = 0
        
        for term, proposed_term in proposals.items():
            if term not in glossary.terms:
                # Brand new term
                proposed_term.source = f"chapter_{chapter_id}_proposal"
                proposed_term.is_canonical = False
                glossary.terms[term] = proposed_term
                new_terms_count += 1
            else:
                existing_term = glossary.terms[term]
                if existing_term.translation == proposed_term.translation:
                    # Duplicate identical term - skip, but can update note if present
                    if proposed_term.note and not existing_term.note:
                        existing_term.note = proposed_term.note
                else:
                    # Mismatching translation! Preserved existing (prioritizing is_canonical)
                    # Create conflict record
                    conflict = GlossaryConflict(
                        term=term,
                        existing_translation=existing_term.translation,
                        existing_source=existing_term.source,
                        proposed_translation=proposed_term.translation,
                        proposed_source=f"chapter_{chapter_id}_proposal",
                        chapter_id=chapter_id,
                    )
                    conflict_report.conflicts.append(conflict)
                    conflicts_count += 1
                    
                    # Print warning to console
                    logger.warning(
                        f"Glossary conflict for '{term}': existing '{existing_term.translation}' ({existing_term.source}) "
                        f"mismatches proposed '{proposed_term.translation}' (chapter_{chapter_id}_proposal). "
                        f"Preserving existing translation."
                    )
                    
        # 5. Write updated glossary and conflict report atomically
        atomic_write_yaml(paths.glossary, glossary)
        if conflict_report.conflicts:
            atomic_write_yaml(paths.glossary_conflicts, conflict_report)
            
        reason = f"Merged glossary proposals for chapter {chapter_id}: added {new_terms_count} terms, recorded {conflicts_count} conflicts."
        
        return OperationResult(
            status=OperationStatus.OK,
            reason=reason,
            report_paths=[str(paths.glossary_conflicts)] if conflict_report.conflicts else [],
        )
    except Exception as error:
        logger.exception("Failed to merge glossary proposals")
        return OperationResult(
            status=OperationStatus.ERROR,
            reason=f"Failed to merge glossary: {error}",
        )


def lock_glossary_term(workspace_root: Path, term: str) -> OperationResult:
    """Manually lock a glossary term, setting is_canonical=True and source=manual."""
    try:
        paths = workspace_paths(workspace_root.parent, workspace_root.name)
        if not paths.glossary.is_file():
            return OperationResult(
                status=OperationStatus.ERROR,
                reason="Glossary file does not exist. Initialize glossary first.",
            )
            
        glossary = load_yaml_model(paths.glossary, BookGlossary)
        if term not in glossary.terms:
            return OperationResult(
                status=OperationStatus.ERROR,
                reason=f"Term '{term}' does not exist in glossary.",
            )
            
        glossary.terms[term].is_canonical = True
        glossary.terms[term].source = "manual"
        atomic_write_yaml(paths.glossary, glossary)
        
        return OperationResult(
            status=OperationStatus.OK,
            reason=f"Term '{term}' successfully locked as canonical.",
            report_paths=[str(paths.glossary)],
        )
    except Exception as error:
        logger.exception("Failed to lock glossary term")
        return OperationResult(
            status=OperationStatus.ERROR,
            reason=f"Failed to lock term: {error}",
        )
