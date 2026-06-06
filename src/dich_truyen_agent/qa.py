from __future__ import annotations

from datetime import datetime
import logging
from pathlib import Path
import re

from dich_truyen_agent.models import (
    BookState,
    ChapterCatalog,
    GlossaryConflictReport,
    QAFinding,
    QAFindingType,
    QAReport,
    StageStatus,
)
from dich_truyen_agent.paths import workspace_paths
from dich_truyen_agent.storage import load_yaml_model

logger = logging.getLogger(__name__)

# Compile CJK ideographs and Chinese punctuation / symbols regex
# \u4e00-\u9fff: CJK Unified Ideographs
# \u3000-\u303f: CJK Symbols and Punctuation (e.g. 。, ，, 、; 「, 」)
CJK_REGEX = re.compile(r"[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]")


def run_qa_check(workspace_root: Path) -> QAReport:
    """Run deterministic read-only QA checks across all translated chapters."""
    workspace_root = workspace_root.resolve()
    paths = workspace_paths(workspace_root.parent, workspace_root.name)

    findings: list[QAFinding] = []
    total_chapters = 0

    # 1. Load catalog and state
    if not paths.chapters.is_file():
        raise FileNotFoundError(f"Missing chapters catalog: {paths.chapters}")
    catalog = load_yaml_model(paths.chapters, ChapterCatalog)

    book_state = None
    if paths.state.is_file():
        book_state = load_yaml_model(paths.state, BookState)
    state_map = {c.chapter_id: c for c in book_state.chapters} if book_state else {}

    # 2. Sequential order & gap verification
    chapter_ids = [entry.chapter_id for entry in catalog.chapters]
    if chapter_ids:
        max_id = max(chapter_ids)
        # Expected contiguous sequence starting at 1
        expected_ids = set(range(1, max_id + 1))
        actual_ids = set(chapter_ids)
        missing_ids = expected_ids - actual_ids
        for mid in sorted(missing_ids):
            findings.append(
                QAFinding(
                    chapter_id=mid,
                    finding_type=QAFindingType.STRUCTURAL,
                    severity="error",
                    message=f"Out-of-order gap: Chapter {mid} is missing from chapters catalog.",
                )
            )

    # 3. Chapter-by-chapter validation
    for entry in catalog.chapters:
        cid = entry.chapter_id
        total_chapters += 1

        # Resolve paths
        raw_path = paths.raw / entry.raw_filename
        trans_path = paths.translations / entry.translation_filename

        # A. Structural check: translation state
        state_record = state_map.get(cid)
        is_completed = (
            state_record
            and state_record.translation.status == StageStatus.COMPLETED
        )

        if not is_completed:
            findings.append(
                QAFinding(
                    chapter_id=cid,
                    finding_type=QAFindingType.STRUCTURAL,
                    severity="error",
                    message=f"Chapter {cid} translation state is not completed (status is '{state_record.translation.status if state_record else 'missing'}').",
                )
            )

        # B. Structural check: file existence
        if not trans_path.is_file():
            findings.append(
                QAFinding(
                    chapter_id=cid,
                    finding_type=QAFindingType.STRUCTURAL,
                    severity="error",
                    message=f"Missing translated file: '{entry.translation_filename}' is not found under translations/.",
                )
            )
            continue

        # C. Structural check: empty files
        try:
            vi_text = trans_path.read_text(encoding="utf-8")
        except OSError as e:
            findings.append(
                QAFinding(
                    chapter_id=cid,
                    finding_type=QAFindingType.STRUCTURAL,
                    severity="error",
                    message=f"Failed to read translated file: {e}",
                )
            )
            continue

        if not vi_text.strip():
            findings.append(
                QAFinding(
                    chapter_id=cid,
                    finding_type=QAFindingType.STRUCTURAL,
                    severity="error",
                    message=f"Translated file is empty: '{entry.translation_filename}'.",
                )
            )
            continue

        # D. Completeness: unbalanced quotes and brackets
        double_quotes = vi_text.count('"')
        if double_quotes % 2 != 0:
            findings.append(
                QAFinding(
                    chapter_id=cid,
                    finding_type=QAFindingType.STRUCTURAL,
                    severity="warning",
                    message="Unbalanced standard double quotes (\") detected.",
                    details={"count": double_quotes},
                )
            )

        cjk_quotes_1 = vi_text.count("「") - vi_text.count("」")
        if cjk_quotes_1 != 0:
            findings.append(
                QAFinding(
                    chapter_id=cid,
                    finding_type=QAFindingType.STRUCTURAL,
                    severity="warning",
                    message=f"Unbalanced CJK quote brackets (「 vs 」: difference is {cjk_quotes_1}).",
                    details={"difference": cjk_quotes_1},
                )
            )

        cjk_quotes_2 = vi_text.count("『") - vi_text.count("』")
        if cjk_quotes_2 != 0:
            findings.append(
                QAFinding(
                    chapter_id=cid,
                    finding_type=QAFindingType.STRUCTURAL,
                    severity="warning",
                    message=f"Unbalanced CJK nested quote brackets (『 vs 』: difference is {cjk_quotes_2}).",
                    details={"difference": cjk_quotes_2},
                )
            )

        parentheses = vi_text.count("(") - vi_text.count(")")
        if parentheses != 0:
            findings.append(
                QAFinding(
                    chapter_id=cid,
                    finding_type=QAFindingType.STRUCTURAL,
                    severity="warning",
                    message=f"Unbalanced parentheses (( vs )): difference is {parentheses}).",
                    details={"difference": parentheses},
                )
            )

        # E. Completeness: missing terminal punctuation
        content = vi_text.strip()
        while content and content[-1] in ('"', "”", "」", "』", ")", "}"):
            content = content[:-1].strip()

        if content and content[-1] not in (".", "!", "?", "…"):
            # Avoid duplicate warnings on short strings that end with custom elements
            if not content.endswith("..."):
                findings.append(
                    QAFinding(
                        chapter_id=cid,
                        finding_type=QAFindingType.STRUCTURAL,
                        severity="warning",
                        message=f"Chapter translation is missing terminal punctuation (ends with '{content[-1]}').",
                        details={"ending_char": content[-1]},
                    )
                )

        # F. Chinese Residue Check
        lines = vi_text.splitlines()
        chapter_residue_count = 0
        max_residue_findings = 50

        for line_idx, line in enumerate(lines, 1):
            if chapter_residue_count >= max_residue_findings:
                findings.append(
                    QAFinding(
                        chapter_id=cid,
                        finding_type=QAFindingType.RESIDUE,
                        severity="warning",
                        message=f"Too many Chinese residue findings. Capping details at {max_residue_findings}.",
                    )
                )
                break

            for match in CJK_REGEX.finditer(line):
                chapter_residue_count += 1
                if chapter_residue_count > max_residue_findings:
                    break

                char = match.group()
                col = match.start() + 1
                snippet_start = max(0, match.start() - 20)
                snippet_end = min(len(line), match.end() + 20)
                snippet = line[snippet_start:snippet_end]

                findings.append(
                    QAFinding(
                        chapter_id=cid,
                        finding_type=QAFindingType.RESIDUE,
                        severity="warning",
                        message=f"Chinese residue '{char}' detected at line {line_idx}, col {col}.",
                        details={
                            "line": line_idx,
                            "column": col,
                            "char": char,
                            "snippet": f"...{snippet}...",
                        },
                    )
                )

        # G. Abnormal character length checks
        if raw_path.is_file():
            try:
                raw_text = raw_path.read_text(encoding="utf-8")
                raw_chars = len(raw_text.strip())
                vi_chars = len(vi_text.strip())

                if raw_chars > 0:
                    ratio = vi_chars / raw_chars
                    if ratio < 0.6 or ratio > 2.0:
                        findings.append(
                            QAFinding(
                                chapter_id=cid,
                                finding_type=QAFindingType.LENGTH,
                                severity="warning",
                                message=f"Abnormal character length ratio of {ratio:.2f} (Vietnamese: {vi_chars} chars, Chinese: {raw_chars} chars).",
                                details={
                                    "ratio": ratio,
                                    "vietnamese_chars": vi_chars,
                                    "chinese_chars": raw_chars,
                                },
                            )
                        )
            except OSError as e:
                findings.append(
                    QAFinding(
                        chapter_id=cid,
                        finding_type=QAFindingType.LENGTH,
                        severity="warning",
                        message=f"Failed to read raw Chinese chapter file to perform length check: {e}",
                    )
                )

    # 4. Unresolved Glossary Conflicts
    if paths.glossary_conflicts.is_file():
        try:
            conflict_report = load_yaml_model(
                paths.glossary_conflicts, GlossaryConflictReport
            )
            for conflict in conflict_report.conflicts:
                findings.append(
                    QAFinding(
                        chapter_id=conflict.chapter_id,
                        finding_type=QAFindingType.GLOSSARY,
                        severity="warning",
                        message=f"Unresolved glossary conflict for '{conflict.term}': existing '{conflict.existing_translation}' vs proposed '{conflict.proposed_translation}'.",
                        details={
                            "term": conflict.term,
                            "existing_translation": conflict.existing_translation,
                            "existing_source": conflict.existing_source,
                            "proposed_translation": conflict.proposed_translation,
                            "proposed_source": conflict.proposed_source,
                        },
                    )
                )
        except Exception as e:
            findings.append(
                QAFinding(
                    chapter_id=1,
                    finding_type=QAFindingType.GLOSSARY,
                    severity="warning",
                    message=f"Failed to parse glossary conflict report: {e}",
                )
            )

    # 5. Compile summary statistics
    error_count = sum(1 for f in findings if f.severity == "error")
    warning_count = sum(1 for f in findings if f.severity == "warning")

    summary = {
        "total_chapters": total_chapters,
        "findings_count": len(findings),
        "error_count": error_count,
        "warning_count": warning_count,
        "passed": error_count == 0,
    }

    return QAReport(
        schema_version=1,
        generated_at=datetime.now(),
        summary=summary,
        findings=findings,
    )
