from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from dich_truyen_agent.models import (
    OperationStatus,
    StageRecord,
    StageStatus,
)
from dich_truyen_agent.paths import workspace_paths
from dich_truyen_agent.storage import atomic_write_yaml, sha256_file
from dich_truyen_agent.workspace import (
    next_translation_work_item,
    promote_chapter_translation,
    verify_staged_chapter,
)
from orchestrator_support import (
    WorkspaceFixture,
    build_crawl_approved_workspace,
)


@pytest.fixture
def workspace_with_crawl_gate(tmp_path: Path) -> WorkspaceFixture:
    return build_crawl_approved_workspace(tmp_path, chapter_count=3)


def test_attempt_paths_are_isolated(workspace_with_crawl_gate: WorkspaceFixture) -> None:
    first = next_translation_work_item(workspace_with_crawl_gate, run_id="run-a", attempt=1)
    second = next_translation_work_item(workspace_with_crawl_gate, run_id="run-a", attempt=2)
    assert first.data["staged_txt"] != second.data["staged_txt"]
    assert second.data["state"] == "pending"
    assert "run-a" in first.data["staged_txt"]
    assert "attempt-01" in first.data["staged_txt"]
    assert "attempt-02" in second.data["staged_txt"]


def test_chapter_1_has_no_predecessor(workspace_with_crawl_gate: WorkspaceFixture) -> None:
    item = next_translation_work_item(workspace_with_crawl_gate, run_id="run-1", attempt=1)
    assert item.status is OperationStatus.OK
    assert item.data["chapter_id"] == 1
    assert item.data["prev_translation_path"] is None


def test_chapter_n_blocks_when_predecessor_file_absent(workspace_with_crawl_gate: WorkspaceFixture) -> None:
    # Mark chapter 1 as completed in state, but do not create the translation file
    state = workspace_with_crawl_gate.reload_state()
    state.chapters[0].translation = StageRecord(
        status=StageStatus.COMPLETED,
        canonical_path="translations/0001-chuong-0001.txt",
        sha256="0" * 64,
    )
    atomic_write_yaml(workspace_with_crawl_gate.state, state)

    item = next_translation_work_item(workspace_with_crawl_gate, run_id="run-1", attempt=1)
    assert item.status is OperationStatus.BLOCKED
    assert "predecessor" in item.reason.lower() or "missing" in item.reason.lower()


def test_chapter_n_blocks_when_predecessor_hash_invalid(workspace_with_crawl_gate: WorkspaceFixture) -> None:
    # Write chapter 1 translation but with mismatching hash
    trans_file = workspace_with_crawl_gate.translation_paths[0]
    trans_file.write_text("# Chương 1 Tiên Nhân Chỉ Lộ\n\nNội dung chương 1.\n", encoding="utf-8")

    state = workspace_with_crawl_gate.reload_state()
    state.chapters[0].translation = StageRecord(
        status=StageStatus.COMPLETED,
        canonical_path="translations/0001-chuong-0001.txt",
        sha256="wronghash" + "0" * 55,
    )
    atomic_write_yaml(workspace_with_crawl_gate.state, state)

    item = next_translation_work_item(workspace_with_crawl_gate, run_id="run-1", attempt=1)
    assert item.status is OperationStatus.BLOCKED
    assert "hash mismatch" in item.reason.lower() or "predecessor" in item.reason.lower()


def test_completed_chapter_after_pending_blocks(workspace_with_crawl_gate: WorkspaceFixture) -> None:
    # Chapter 1 pending, Chapter 2 completed
    trans_file = workspace_with_crawl_gate.translation_paths[1]
    trans_file.write_text("# Chương 2 Luyện Khí Nhập Thể\n\nNội dung chương 2.\n", encoding="utf-8")

    state = workspace_with_crawl_gate.reload_state()
    state.chapters[1].translation = StageRecord(
        status=StageStatus.COMPLETED,
        canonical_path="translations/0002-chuong-0002.txt",
        sha256=sha256_file(trans_file),
    )
    atomic_write_yaml(workspace_with_crawl_gate.state, state)

    item = next_translation_work_item(workspace_with_crawl_gate, run_id="run-1", attempt=1)
    assert item.status is OperationStatus.BLOCKED
    assert "translation state gap" in item.reason


def test_verify_staged_chapter_enforces_run_staging_directory(workspace_with_crawl_gate: WorkspaceFixture) -> None:
    # Outside run staging directory (e.g. legacy staging path or path traversal)
    bad_path = workspace_with_crawl_gate.root / "staging" / "chuong-0001-staged.txt"
    bad_path.parent.mkdir(parents=True, exist_ok=True)
    bad_path.write_text("# Chương 1 Tiêu Đề\n\nNội dung.\n", encoding="utf-8")

    res = verify_staged_chapter(
        workspace_with_crawl_gate.root,
        1,
        run_id="run-a",
        attempt=1,
        staged_txt_path=bad_path,
    )
    assert res.status is OperationStatus.ERROR
    assert "staging" in res.reason.lower() or "canonical" in res.reason.lower()


def test_leftover_fixed_name_staging_cannot_satisfy_new_attempt(workspace_with_crawl_gate: WorkspaceFixture) -> None:
    # Legacy fixed staging file exists
    paths = workspace_paths(workspace_with_crawl_gate.root.parent, workspace_with_crawl_gate.root.name)
    legacy_file = paths.staging / "chuong-0001-staged.txt"
    legacy_file.parent.mkdir(parents=True, exist_ok=True)
    legacy_file.write_text("# Chương 1 Tiêu Đề\n\nNội dung cũ.\n", encoding="utf-8")

    # verify with run_id and attempt=1 must look at run staging, not legacy file
    res = verify_staged_chapter(
        workspace_with_crawl_gate.root,
        1,
        run_id="run-b",
        attempt=1,
    )
    assert res.status is OperationStatus.ERROR
    assert "missing" in res.reason.lower()

    # promote with run_id and attempt=1 must also fail
    promote_res = promote_chapter_translation(
        workspace_with_crawl_gate.root,
        1,
        run_id="run-b",
        attempt=1,
    )
    assert promote_res.status is OperationStatus.ERROR
    assert "not found" in promote_res.reason.lower() or "missing" in promote_res.reason.lower()


def test_verify_staged_chapter_structural_checks(workspace_with_crawl_gate: WorkspaceFixture) -> None:
    run_staging = workspace_with_crawl_gate.root / "reports" / "runs" / "run-x" / "staging"
    run_staging.mkdir(parents=True, exist_ok=True)
    staged_txt = run_staging / "chuong-0001-attempt-01-staged.txt"

    # 1. Empty text
    staged_txt.write_text("", encoding="utf-8")
    res = verify_staged_chapter(workspace_with_crawl_gate.root, 1, run_id="run-x", attempt=1)
    assert res.status is OperationStatus.ERROR
    assert "empty" in res.reason.lower()

    # 2. Invalid heading
    staged_txt.write_text("Chương 1 không có dấu thăng\n\nNội dung.", encoding="utf-8")
    res = verify_staged_chapter(workspace_with_crawl_gate.root, 1, run_id="run-x", attempt=1)
    assert res.status is OperationStatus.ERROR
    assert "line 1" in res.reason.lower()

    # 3. Mismatched chapter id
    staged_txt.write_text("# Chương 2 Tiêu Đề Sai\n\nNội dung.", encoding="utf-8")
    res = verify_staged_chapter(workspace_with_crawl_gate.root, 1, run_id="run-x", attempt=1)
    assert res.status is OperationStatus.ERROR
    assert "line 1" in res.reason.lower()

    # 4. Missing blank line at line 2
    staged_txt.write_text("# Chương 1 Tiêu Đề Đúng\nNội dung dính liền.", encoding="utf-8")
    res = verify_staged_chapter(workspace_with_crawl_gate.root, 1, run_id="run-x", attempt=1)
    assert res.status is OperationStatus.ERROR
    assert "line 2 must be blank" in res.reason.lower()

    # 5. Valid structure
    staged_txt.write_text("# Chương 1 Tiên Nhân Chỉ Lộ\n\nNội dung chương 1 dịch chuẩn xác.\n", encoding="utf-8")
    res = verify_staged_chapter(workspace_with_crawl_gate.root, 1, run_id="run-x", attempt=1)
    assert res.status is OperationStatus.OK
    assert res.data["ok"] is True


def test_promote_attempt_scoped_compact_result(workspace_with_crawl_gate: WorkspaceFixture) -> None:
    run_staging = workspace_with_crawl_gate.root / "reports" / "runs" / "run-x" / "staging"
    run_staging.mkdir(parents=True, exist_ok=True)
    staged_txt = run_staging / "chuong-0001-attempt-01-staged.txt"
    staged_yaml = run_staging / "chuong-0001-attempt-01-proposals.yaml"

    staged_txt.write_text("# Chương 1 Tiên Nhân Chỉ Lộ\n\nNội dung dịch tuyệt vời.\n", encoding="utf-8")
    staged_yaml.write_text(yaml.safe_dump({"仙人": {"translation": "Tiên Nhân", "category": "character"}}), encoding="utf-8")

    res = promote_chapter_translation(
        workspace_with_crawl_gate.root,
        1,
        run_id="run-x",
        attempt=1,
    )
    assert res.status is OperationStatus.OK
    # Ensure OperationResult is compact and does not contain translated text
    res_json = res.model_dump_json()
    assert "Nội dung dịch tuyệt vời" not in res_json

    # Translation is in canonical translations/ directory
    promoted = workspace_with_crawl_gate.root / "translations" / "0001-chuong-0001.txt"
    assert promoted.is_file()
    assert promoted.read_text(encoding="utf-8").startswith("# Chương 1 Tiên Nhân Chỉ Lộ")
