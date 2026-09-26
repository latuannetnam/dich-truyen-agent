from __future__ import annotations

from pathlib import Path
import pytest

from dich_truyen_agent.checkpoints import (
    approve_current_qa,
    approve_full_crawl,
    check_orchestrator_gate,
)
from dich_truyen_agent.models import (
    ApprovalScope,
    BookMetadata,
    BookState,
    ChapterCatalog,
    ChapterCatalogEntry,
    ChapterState,
    CheckpointRecord,
    CheckpointType,
    CrawlReport,
    DiscoveredChapter,
    OperationStatus,
    QAFinding,
    QAFindingType,
    QAReport,
    StageRecord,
    StageStatus,
    TranslationStyle,
)
from dich_truyen_agent.orchestrator.graph import (
    _compute_crawl_evidence_hashes,
    _compute_qa_evidence_hashes,
)
from dich_truyen_agent.paths import chapter_filename, workspace_paths
from dich_truyen_agent.scope import build_source_scope, save_source_scope
from dich_truyen_agent.storage import (
    atomic_write_text,
    atomic_write_yaml,
    load_yaml_model,
    sha256_file,
)


def setup_scoped_workspace(
    root: Path,
    slug: str = "scoped-gate-book",
    scope_managed: bool = True,
    create_scope_file: bool = True,
    with_translations: bool = False,
) -> tuple[Path, ChapterCatalog]:
    paths = workspace_paths(root, slug)
    paths.root.mkdir(parents=True, exist_ok=True)
    paths.raw.mkdir(parents=True, exist_ok=True)
    paths.translations.mkdir(parents=True, exist_ok=True)
    paths.reports.mkdir(parents=True, exist_ok=True)
    paths.checkpoints.mkdir(parents=True, exist_ok=True)

    metadata = BookMetadata(
        book_slug=slug,
        source_url="https://example.com/novel/index.html",
        title="Scoped Gate Novel",
        author="Author",
        scope_managed=scope_managed,
    )
    atomic_write_yaml(paths.book, metadata)

    style = TranslationStyle(
        name="general",
        description="General",
        guidelines=[],
        vocabulary={},
        tone="natural",
        examples=[],
    )
    atomic_write_yaml(paths.style, style)

    discovered = [
        DiscoveredChapter(
            position=i,
            source_id=f"ch-{i}",
            source_url=f"https://example.com/novel/ch-{i}.html",
            original_title=f"第{i}章 章节{i}",
            parsed_ordinal=i,
        )
        for i in range(1, 6)
    ]

    if create_scope_file:
        scope_rec = build_source_scope(
            discovered,
            metadata.source_url,
            limit=3 if scope_managed else None,
        )
        save_source_scope(paths.source_scope, scope_rec)

    count = 3 if scope_managed else 5
    entries = []
    state_chapters = []
    for i in range(1, count + 1):
        fn = chapter_filename(i, f"第{i}章 章节{i}")
        slug_i = fn[5:-4]
        entries.append(
            ChapterCatalogEntry(
                chapter_id=i,
                slug=slug_i,
                source_url=f"https://example.com/novel/ch-{i}.html",
                original_title=f"第{i}章 章节{i}",
                raw_filename=fn,
                translation_filename=fn,
            )
        )
        # Write valid raw file
        raw_text = f"第{i}章 章节{i}\n\n" + ("Valid raw text body. " * 30)
        atomic_write_text(paths.raw / fn, raw_text)
        raw_hash = sha256_file(paths.raw / fn)

        trans_record = StageRecord()
        if with_translations:
            trans_text = f"Chương {i}: Tiêu đề {i}\n\n" + (
                "Nội dung tiếng Việt hợp lệ dài đủ tiêu chuẩn. " * 20
            )
            atomic_write_text(paths.translations / fn, trans_text)
            trans_hash = sha256_file(paths.translations / fn)
            trans_record = StageRecord(
                status=StageStatus.COMPLETED,
                canonical_path=f"translations/{fn}",
                sha256=trans_hash,
            )

        state_chapters.append(
            ChapterState(
                chapter_id=i,
                raw=StageRecord(
                    status=StageStatus.COMPLETED,
                    canonical_path=f"raw/{fn}",
                    sha256=raw_hash,
                ),
                translation=trans_record,
            )
        )

    catalog = ChapterCatalog(chapters=entries)
    atomic_write_yaml(paths.chapters, catalog)

    book_state = BookState(chapters=state_chapters)
    atomic_write_yaml(paths.state, book_state)

    crawl_report = CrawlReport(
        discovered_count=count,
        selected_count=count,
        completed_count=count,
        failed_count=0,
        max_chapters=0,
        active_profile_source="shared",
        source_discovered_count=5 if scope_managed else None,
        scope=ApprovalScope.FULL,
        scope_summary=f"prefix {count} of 5" if scope_managed else None,
        warnings=[],
        blockers=[],
    )
    atomic_write_yaml(paths.crawl_report, crawl_report)

    if with_translations:
        qa_report = QAReport(
            summary={"error_count": 0, "warning_count": 0, "findings_count": 0},
            findings=[],
        )
        atomic_write_yaml(paths.reports / "qa-report.yaml", qa_report)

    return paths.root, catalog


def test_approve_full_crawl_scoped_evidence_and_gate_tampering(tmp_path: Path) -> None:
    ws_root, _ = setup_scoped_workspace(tmp_path / "books")
    paths = workspace_paths(tmp_path / "books", "scoped-gate-book")

    res = approve_full_crawl(ws_root)
    assert res.status == OperationStatus.OK, res.reason

    # Verify evidence hashes contain reports/source-scope.yaml
    ckpt_path = paths.checkpoint("crawl-approved")
    record = load_yaml_model(ckpt_path, CheckpointRecord)
    assert "reports/source-scope.yaml" in record.evidence_hashes

    # Gate check passes
    gate_res = check_orchestrator_gate(ws_root, CheckpointType.CRAWL_APPROVED)
    assert gate_res.status == OperationStatus.OK, gate_res.reason

    # Changing source-scope blocks the gate
    orig_text = paths.source_scope.read_text(encoding="utf-8")
    paths.source_scope.write_text(orig_text + "\n# tampered", encoding="utf-8")

    tampered_res = check_orchestrator_gate(ws_root, CheckpointType.CRAWL_APPROVED)
    assert tampered_res.status == OperationStatus.BLOCKED
    assert (
        "stale" in tampered_res.reason.lower()
        or "evidence" in tampered_res.reason.lower()
    )

    # Deleting source-scope blocks the gate
    paths.source_scope.unlink()
    deleted_res = check_orchestrator_gate(ws_root, CheckpointType.CRAWL_APPROVED)
    assert deleted_res.status == OperationStatus.BLOCKED


def test_approve_current_qa_scoped_evidence_and_gate_tampering(tmp_path: Path) -> None:
    ws_root, _ = setup_scoped_workspace(
        tmp_path / "books",
        slug="qa-gate-book",
        with_translations=True,
    )
    paths = workspace_paths(tmp_path / "books", "qa-gate-book")

    res = approve_current_qa(ws_root)
    assert res.status == OperationStatus.OK, res.reason

    # Verify evidence hashes contain reports/source-scope.yaml
    ckpt_path = paths.checkpoint("qa-approved")
    record = load_yaml_model(ckpt_path, CheckpointRecord)
    assert "reports/source-scope.yaml" in record.evidence_hashes

    # Gate check passes
    gate_res = check_orchestrator_gate(ws_root, CheckpointType.QA_APPROVED)
    assert gate_res.status == OperationStatus.OK, gate_res.reason

    # Changing source-scope blocks the gate
    orig_text = paths.source_scope.read_text(encoding="utf-8")
    paths.source_scope.write_text(orig_text + "\n# tampered", encoding="utf-8")

    tampered_res = check_orchestrator_gate(ws_root, CheckpointType.QA_APPROVED)
    assert tampered_res.status == OperationStatus.BLOCKED

    # Deleting source-scope blocks the gate
    paths.source_scope.unlink()
    deleted_res = check_orchestrator_gate(ws_root, CheckpointType.QA_APPROVED)
    assert deleted_res.status == OperationStatus.BLOCKED


def test_scope_managed_missing_scope_file_blocks_approval(tmp_path: Path) -> None:
    ws_root, _ = setup_scoped_workspace(
        tmp_path / "books",
        slug="missing-scope-approval",
        scope_managed=True,
        create_scope_file=False,
    )
    res = approve_full_crawl(ws_root)
    assert res.status == OperationStatus.BLOCKED
    assert "source-scope" in res.reason.lower()

    qa_res = approve_current_qa(ws_root)
    assert qa_res.status == OperationStatus.BLOCKED
    assert "source-scope" in qa_res.reason.lower()


def test_scope_managed_scope_digest_mismatch_blocks_approval(tmp_path: Path) -> None:
    ws_root, catalog = setup_scoped_workspace(
        tmp_path / "books",
        slug="mismatched-scope-book",
        scope_managed=True,
        create_scope_file=True,
    )
    paths = workspace_paths(tmp_path / "books", "mismatched-scope-book")

    # Tamper scope file so it points to different source URLs
    tampered_discovered = [
        DiscoveredChapter(
            position=i,
            source_id=f"ch-{i}",
            source_url=f"https://different-site.com/ch-{i}.html",
            original_title=f"第{i}章 章节{i}",
            parsed_ordinal=i,
        )
        for i in range(1, 6)
    ]
    tampered_scope = build_source_scope(
        tampered_discovered, "https://different-site.com/index.html", limit=3
    )
    save_source_scope(paths.source_scope, tampered_scope)

    res = approve_full_crawl(ws_root)
    assert res.status == OperationStatus.BLOCKED
    assert "scope" in res.reason.lower()

    qa_res = approve_current_qa(ws_root)
    assert qa_res.status == OperationStatus.BLOCKED
    assert "scope" in qa_res.reason.lower()


def test_legacy_workspace_passes_without_scope_file(tmp_path: Path) -> None:
    ws_root, _ = setup_scoped_workspace(
        tmp_path / "books",
        slug="legacy-gate-book",
        scope_managed=False,
        create_scope_file=False,
        with_translations=True,
    )
    res = approve_full_crawl(ws_root)
    assert res.status == OperationStatus.OK, res.reason

    paths = workspace_paths(tmp_path / "books", "legacy-gate-book")
    crawl_record = load_yaml_model(paths.checkpoint("crawl-approved"), CheckpointRecord)
    assert "reports/source-scope.yaml" not in crawl_record.evidence_hashes

    gate_res = check_orchestrator_gate(ws_root, CheckpointType.CRAWL_APPROVED)
    assert gate_res.status == OperationStatus.OK, gate_res.reason

    qa_res = approve_current_qa(ws_root)
    assert qa_res.status == OperationStatus.OK, qa_res.reason
    qa_record = load_yaml_model(paths.checkpoint("qa-approved"), CheckpointRecord)
    assert "reports/source-scope.yaml" not in qa_record.evidence_hashes

    qa_gate_res = check_orchestrator_gate(ws_root, CheckpointType.QA_APPROVED)
    assert qa_gate_res.status == OperationStatus.OK, qa_gate_res.reason


def test_qa_warning_manual_allow_warnings_records_partial_scope_and_passes_gate(
    tmp_path: Path,
) -> None:
    ws_root, _ = setup_scoped_workspace(
        tmp_path / "books",
        slug="qa-warnings-book",
        with_translations=True,
    )
    paths = workspace_paths(tmp_path / "books", "qa-warnings-book")

    # Create QA report with a warning
    qa_rep = QAReport(
        summary={"error_count": 0, "warning_count": 1, "findings_count": 1},
        findings=[
            QAFinding(
                chapter_id=1,
                finding_type=QAFindingType.LENGTH,
                severity="warning",
                message="Unusually short chapter",
            )
        ],
    )
    atomic_write_yaml(paths.reports / "qa-report.yaml", qa_rep)

    # Disallow warnings -> blocked
    res_disallowed = approve_current_qa(ws_root, report=qa_rep, allow_warnings=False)
    assert res_disallowed.status == OperationStatus.BLOCKED

    # Allow warnings -> succeeds with partial scope
    res_allowed = approve_current_qa(ws_root, report=qa_rep, allow_warnings=True)
    assert res_allowed.status == OperationStatus.OK, res_allowed.reason

    record = load_yaml_model(paths.checkpoint("qa-approved"), CheckpointRecord)
    assert record.scope == ApprovalScope.PARTIAL

    # check_orchestrator_gate passes
    gate_res = check_orchestrator_gate(ws_root, CheckpointType.QA_APPROVED)
    assert gate_res.status == OperationStatus.OK, gate_res.reason


def test_graph_evidence_hashes_scoped_and_missing(tmp_path: Path) -> None:
    ws_root, _ = setup_scoped_workspace(
        tmp_path / "books",
        slug="graph-evidence-book",
        scope_managed=True,
        create_scope_file=True,
        with_translations=True,
    )
    paths = workspace_paths(tmp_path / "books", "graph-evidence-book")

    crawl_hashes = _compute_crawl_evidence_hashes(ws_root)
    assert "reports/source-scope.yaml" in crawl_hashes

    qa_hashes = _compute_qa_evidence_hashes(ws_root)
    assert "reports/source-scope.yaml" in qa_hashes

    # Deleting source-scope causes _compute_* to raise ValueError when require_scope=True
    paths.source_scope.unlink()
    with pytest.raises(ValueError, match="source-scope"):
        _compute_crawl_evidence_hashes(ws_root)

    with pytest.raises(ValueError, match="source-scope"):
        _compute_qa_evidence_hashes(ws_root)
