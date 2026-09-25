from pathlib import Path

import pytest

from dich_truyen_agent.checkpoints import (
    approve_checkpoint,
    approve_full_crawl,
    check_gate,
    require_checkpoint_scope,
)
from dich_truyen_agent.models import (
    ApprovalScope,
    BookMetadata,
    ChapterCatalog,
    CheckpointRecord,
    CheckpointType,
    CrawlReport,
    OperationStatus,
    TranslationStyle,
)
from dich_truyen_agent.paths import workspace_paths
from dich_truyen_agent.storage import load_yaml_model
from dich_truyen_agent.workspace import initialize_workspace
from orchestrator_support import WorkspaceFixture, build_full_crawl_workspace


@pytest.fixture
def workspace_root(
    books_root: Path,
    metadata: BookMetadata,
    catalog: ChapterCatalog,
    style: TranslationStyle,
) -> Path:
    initialize_workspace(books_root, metadata, catalog, style)
    return workspace_paths(books_root, metadata.book_slug).root


def test_missing_checkpoint_blocks_with_expected_path(workspace_root: Path) -> None:
    result = check_gate(workspace_root, CheckpointType.CRAWL_APPROVED)
    assert result.status is OperationStatus.BLOCKED
    assert "crawl-approved" in result.reason
    assert result.approval_path == "checkpoints/crawl-approved.yaml"


def test_explicit_approval_persists_record_and_allows_gate(workspace_root: Path) -> None:
    report = workspace_root / "reports" / "crawl.yaml"
    evidence = workspace_root / "raw" / "0001.txt"
    report.write_text("review", encoding="utf-8")
    evidence.write_text("body", encoding="utf-8")

    approved = approve_checkpoint(
        workspace_root,
        CheckpointType.CRAWL_APPROVED,
        "reports/crawl.yaml",
        ["raw/0001.txt"],
    )
    record = load_yaml_model(
        workspace_root / "checkpoints" / "crawl-approved.yaml", CheckpointRecord
    )
    checked = check_gate(workspace_root, CheckpointType.CRAWL_APPROVED)

    assert approved.status is OperationStatus.OK
    assert record.report_path == "reports/crawl.yaml"
    assert set(record.evidence_hashes) == {"raw/0001.txt"}
    assert checked.status is OperationStatus.OK


@pytest.mark.parametrize("mutation", ["changed", "removed"])
def test_gate_blocks_stale_evidence(workspace_root: Path, mutation: str) -> None:
    report = workspace_root / "reports" / "crawl.yaml"
    evidence = workspace_root / "raw" / "0001.txt"
    report.write_text("review", encoding="utf-8")
    evidence.write_text("body", encoding="utf-8")
    approve_checkpoint(
        workspace_root,
        CheckpointType.CRAWL_APPROVED,
        "reports/crawl.yaml",
        ["raw/0001.txt"],
    )
    if mutation == "changed":
        evidence.write_text("changed", encoding="utf-8")
    else:
        evidence.unlink()

    result = check_gate(workspace_root, CheckpointType.CRAWL_APPROVED)

    assert result.status is OperationStatus.BLOCKED
    assert "stale" in result.reason


def test_approval_rejects_workspace_escape(workspace_root: Path) -> None:
    with pytest.raises(ValueError):
        approve_checkpoint(
            workspace_root,
            CheckpointType.CRAWL_APPROVED,
            "../outside.yaml",
            ["../outside.txt"],
        )


def test_gate_blocks_malformed_checkpoint_yaml(workspace_root: Path) -> None:
    approval = workspace_root / "checkpoints" / "crawl-approved.yaml"
    approval.write_text("not: valid: yaml", encoding="utf-8")
    result = check_gate(workspace_root, CheckpointType.CRAWL_APPROVED)
    assert result.status is OperationStatus.BLOCKED
    assert "stale or invalid" in result.reason


def test_checkpoint_scope_verification(workspace_root: Path) -> None:
    report = workspace_root / "reports" / "crawl.yaml"
    evidence = workspace_root / "raw" / "0001.txt"
    report.write_text("review", encoding="utf-8")
    evidence.write_text("body", encoding="utf-8")

    # 1. Partial scope checkpoint
    approve_checkpoint(
        workspace_root,
        CheckpointType.CRAWL_APPROVED,
        "reports/crawl.yaml",
        ["raw/0001.txt"],
        scope=ApprovalScope.PARTIAL,
    )

    # Partial scope requirement is allowed
    assert require_checkpoint_scope(workspace_root, CheckpointType.CRAWL_APPROVED, ApprovalScope.PARTIAL).status is OperationStatus.OK
    # Full scope requirement is blocked on partial checkpoint
    assert require_checkpoint_scope(workspace_root, CheckpointType.CRAWL_APPROVED, ApprovalScope.FULL).status is OperationStatus.BLOCKED

    # 2. Full scope checkpoint
    approve_checkpoint(
        workspace_root,
        CheckpointType.CRAWL_APPROVED,
        "reports/crawl.yaml",
        ["raw/0001.txt"],
        scope=ApprovalScope.FULL,
    )

    # Full scope requirement is allowed on full checkpoint
    assert require_checkpoint_scope(workspace_root, CheckpointType.CRAWL_APPROVED, ApprovalScope.FULL).status is OperationStatus.OK


@pytest.fixture
def full_crawl_workspace(tmp_path: Path) -> WorkspaceFixture:
    return build_full_crawl_workspace(tmp_path, chapter_count=2)


def test_new_crawl_gate_tracks_catalog_not_mutable_state(full_crawl_workspace: WorkspaceFixture) -> None:
    report = load_yaml_model(full_crawl_workspace.report, CrawlReport)
    result = approve_full_crawl(full_crawl_workspace.root, report)
    assert result.status is OperationStatus.OK
    full_crawl_workspace.promote_first_translation()
    assert check_gate(full_crawl_workspace.root, CheckpointType.CRAWL_APPROVED).status is OperationStatus.OK


def test_approve_full_crawl_rejects_empty_catalog(tmp_path: Path) -> None:
    wf = build_full_crawl_workspace(tmp_path, chapter_count=0)
    report = load_yaml_model(wf.report, CrawlReport)
    result = approve_full_crawl(wf.root, report)
    assert result.status is OperationStatus.BLOCKED
    assert "discovered" in result.reason.lower() or "catalog" in result.reason.lower() or "0" in result.reason


def test_approve_full_crawl_rejects_partial_crawl(full_crawl_workspace: WorkspaceFixture) -> None:
    report = load_yaml_model(full_crawl_workspace.report, CrawlReport)
    report.scope = ApprovalScope.PARTIAL
    report.max_chapters = 1
    result = approve_full_crawl(full_crawl_workspace.root, report)
    assert result.status is OperationStatus.BLOCKED
    assert "full" in result.reason.lower() or "partial" in result.reason.lower()


def test_approve_full_crawl_rejects_missing_raw_chapter(full_crawl_workspace: WorkspaceFixture) -> None:
    report = load_yaml_model(full_crawl_workspace.report, CrawlReport)
    full_crawl_workspace.raw_paths[0].unlink()
    result = approve_full_crawl(full_crawl_workspace.root, report)
    assert result.status is OperationStatus.BLOCKED
    assert "missing" in result.reason.lower() or "raw" in result.reason.lower()


def test_approve_full_crawl_rejects_blockers(full_crawl_workspace: WorkspaceFixture) -> None:
    report = load_yaml_model(full_crawl_workspace.report, CrawlReport)
    report.blockers = ["Chapter 1 body is corrupt"]
    result = approve_full_crawl(full_crawl_workspace.root, report)
    assert result.status is OperationStatus.BLOCKED
    assert "blocked" in result.reason.lower() or "findings" in result.reason.lower()


def test_orchestrator_gate_blocks_old_approval_missing_catalog(workspace_root: Path) -> None:
    report = workspace_root / "reports" / "crawl.yaml"
    evidence = workspace_root / "raw" / "0001.txt"
    report.parent.mkdir(parents=True, exist_ok=True)
    evidence.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("review", encoding="utf-8")
    evidence.write_text("body", encoding="utf-8")

    approve_checkpoint(
        workspace_root,
        CheckpointType.CRAWL_APPROVED,
        "reports/crawl.yaml",
        ["raw/0001.txt"],
    )

    result = check_gate(workspace_root, CheckpointType.CRAWL_APPROVED, strict=True)
    assert result.status is OperationStatus.BLOCKED
    assert "chapters.yaml" in result.reason
    assert "regenerat" in result.reason.lower() or "re-approval" in result.reason.lower()

