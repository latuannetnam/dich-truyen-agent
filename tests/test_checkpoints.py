from pathlib import Path

import pytest

from dich_truyen_agent.checkpoints import approve_checkpoint, check_gate
from dich_truyen_agent.models import (
    BookMetadata,
    ChapterCatalog,
    CheckpointRecord,
    CheckpointType,
    OperationStatus,
    TranslationStyle,
)
from dich_truyen_agent.paths import workspace_paths
from dich_truyen_agent.storage import load_yaml_model
from dich_truyen_agent.workspace import initialize_workspace


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
