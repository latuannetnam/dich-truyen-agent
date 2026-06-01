from __future__ import annotations

import logging
from pathlib import Path

from dich_truyen_agent.models import (
    BookGlossary,
    GlossaryTerm,
    GlossaryConflict,
    GlossaryConflictReport,
    OperationResult,
    OperationStatus,
)
from dich_truyen_agent.paths import workspace_paths
from dich_truyen_agent.storage import atomic_write_yaml, load_yaml_model

logger = logging.getLogger(__name__)


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
