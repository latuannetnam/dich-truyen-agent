from __future__ import annotations

import re
from pathlib import Path

from dich_truyen_agent.crawler import validate_discovered_catalog
from dich_truyen_agent.models import (
    ApprovalScope,
    BookState,
    ChapterCatalog,
    CrawlProfile,
    CrawlReport,
    CrawlSettings,
    StageStatus,
)
from dich_truyen_agent.paths import validate_workspace_relative_path, workspace_paths
from dich_truyen_agent.storage import load_yaml_model


def build_crawl_report(
    workspace_root: Path,
    active_profile: CrawlProfile,
    settings: CrawlSettings,
) -> CrawlReport:
    """Audit workspace crawl results and build a structured CrawlReport."""
    workspace_root = Path(workspace_root).resolve()
    paths = workspace_paths(workspace_root.parent, workspace_root.name)

    # 1. Load catalog and state
    catalog = load_yaml_model(paths.chapters, ChapterCatalog)
    state = load_yaml_model(paths.state, BookState)

    # Determine scope
    max_chapters = settings.max_chapters
    target_chapters = catalog.chapters
    if max_chapters > 0:
        target_chapters = catalog.chapters[:max_chapters]

    discovered_count = len(catalog.chapters)
    selected_count = len(target_chapters)

    # Process counts and status from state
    state_by_id = {c.chapter_id: c for c in state.chapters}
    
    completed_count = 0
    failed_count = 0
    
    blockers = []
    warnings = []
    chapter_lengths = {}
    residue_findings = {}
    excerpts = {}

    # Catalog validation checks
    discovered_chapters = []
    # Rebuild discovered chapters mock list for validation
    from urllib.parse import urlparse
    from dich_truyen_agent.crawler import parse_chapter_ordinal, DiscoveredChapter
    for c in catalog.chapters:
        parsed = urlparse(c.source_url)
        source_id = parsed.path.strip("/")
        if not source_id:
            source_id = c.source_url

        discovered_chapters.append(
            DiscoveredChapter(
                position=c.chapter_id,
                source_id=source_id,
                source_url=c.source_url,
                original_title=c.original_title,
                parsed_ordinal=parse_chapter_ordinal(c.original_title)
            )
        )
    
    cat_val = validate_discovered_catalog(discovered_chapters)
    blockers.extend(cat_val["blockers"])
    warnings.extend(cat_val["warnings"])

    # 2. Check each target chapter's status and raw file
    for tc in target_chapters:
        c_state = state_by_id.get(tc.chapter_id)
        if not c_state:
            blockers.append(f"Chapter {tc.chapter_id} is missing state record")
            continue

        raw_stage = c_state.raw
        if raw_stage.status is StageStatus.COMPLETED:
            completed_count += 1
            if not raw_stage.canonical_path:
                blockers.append(f"Chapter {tc.chapter_id} is marked complete but missing canonical path")
                continue

            try:
                raw_file = validate_workspace_relative_path(paths.root, raw_stage.canonical_path)
            except Exception as e:
                blockers.append(f"Chapter {tc.chapter_id} canonical path is invalid: {e}")
                continue

            if not raw_file.is_file():
                blockers.append(f"Chapter {tc.chapter_id} raw file is missing: {raw_stage.canonical_path}")
                continue

            try:
                text = raw_file.read_text(encoding="utf-8")
            except Exception as e:
                blockers.append(f"Chapter {tc.chapter_id} raw file is unreadable: {e}")
                continue

            char_len = len(text)
            chapter_lengths[str(tc.chapter_id)] = char_len

            if char_len == 0:
                blockers.append(f"Chapter {tc.chapter_id} raw file is empty")
            elif char_len < 300:
                warnings.append(f"Chapter {tc.chapter_id} raw body is unusually short ({char_len} chars)")

            # Check for suspicious residue (HTML tags, script leftovers, cloudflare garbage)
            residue = []
            if "<" in text and ">" in text:
                residue.append("html_tags")
            if "javascript" in text.lower() or "console.log" in text.lower():
                residue.append("script_residue")
            if "cloudflare" in text.lower():
                residue.append("cloudflare_markers")
            
            if residue:
                residue_findings[str(tc.chapter_id)] = residue
                warnings.append(f"Chapter {tc.chapter_id} contains potential residue: {residue}")

        elif raw_stage.status is StageStatus.ERROR:
            failed_count += 1
            blockers.append(f"Chapter {tc.chapter_id} crawl failed: {raw_stage.error}")
        else:
            blockers.append(f"Chapter {tc.chapter_id} download is pending")

    # 3. Excerpts Generation (beginning, middle, end)
    completed_chapters = [
        tc for tc in target_chapters
        if state_by_id.get(tc.chapter_id) and state_by_id[tc.chapter_id].raw.status is StageStatus.COMPLETED
    ]
    
    if completed_chapters:
        excerpt_positions = []
        # Beginning
        excerpt_positions.append(completed_chapters[0])
        # Middle
        if len(completed_chapters) > 2:
            excerpt_positions.append(completed_chapters[len(completed_chapters) // 2])
        # End
        if len(completed_chapters) > 1:
            excerpt_positions.append(completed_chapters[-1])

        for tc in excerpt_positions:
            c_state = state_by_id[tc.chapter_id]
            try:
                raw_file = validate_workspace_relative_path(paths.root, c_state.raw.canonical_path or "")
                text = raw_file.read_text(encoding="utf-8")
                
                # Excerpt sections: beginning, middle, end of the chapter itself
                beg_slice = text[:200].strip()
                mid_start = max(0, len(text) // 2 - 100)
                mid_slice = text[mid_start:mid_start+200].strip()
                end_slice = text[-200:].strip()

                excerpts[str(tc.chapter_id)] = {
                    "beginning": beg_slice,
                    "middle": mid_slice,
                    "end": end_slice,
                }
            except Exception:
                pass

    # 4. Scope determination
    scope = ApprovalScope.FULL
    if max_chapters > 0 and max_chapters < discovered_count:
        scope = ApprovalScope.PARTIAL

    # Determine profile source location for metadata
    profile_source_str = "local_override" if (paths.root / "crawl-profile.yaml").exists() else "shared_template"

    return CrawlReport(
        schema_version=1,
        discovered_count=discovered_count,
        selected_count=selected_count,
        completed_count=completed_count,
        failed_count=failed_count,
        max_chapters=max_chapters,
        scope=scope,
        active_profile_source=profile_source_str,
        blockers=blockers,
        warnings=warnings,
        chapter_lengths=chapter_lengths,
        suspicious_residue_findings=residue_findings,
        excerpts=excerpts,
    )


def approval_blockers(report: CrawlReport) -> list[str]:
    """Extract blockers that refuse crawl approval."""
    return report.blockers
