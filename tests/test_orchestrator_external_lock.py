from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock
import pytest

from dich_truyen_agent.models import OperationResult, OperationStatus
from dich_truyen_agent.orchestrator.models import OrchestratorConfig
from dich_truyen_agent.orchestrator.orchestrator import (
    BookOrchestrator,
    WorkspaceLock,
    _lock_path,
)
from dich_truyen_agent.orchestrator.runners.mock import MockRunner
from dich_truyen_agent.orchestrator.workspace_ops import WorkspaceOps
from orchestrator_support import build_initialized_workspace


def test_lock_path_resolution_and_release_retains_file(tmp_path: Path) -> None:
    books_root = tmp_path / "books"
    slug = "test-book"
    workspace_root = books_root / slug

    # Assert _lock_path resolves before workspace exists
    assert not workspace_root.exists()
    lock_file = _lock_path(workspace_root)
    expected_lock_file = books_root / ".orchestrator-locks" / f"{slug}.lock"
    assert lock_file == expected_lock_file

    # Acquire and release with WorkspaceLock
    lock1 = WorkspaceLock(lock_file)
    assert lock1.acquire() is True
    assert lock_file.is_file()

    # Second lock fails while lock1 is held
    lock2 = WorkspaceLock(lock_file)
    assert lock2.acquire() is False

    # Release leaves lock file on disk
    lock1.release()
    assert lock_file.is_file()

    # Second lock can now acquire
    assert lock2.acquire() is True
    lock2.release()
    assert lock_file.is_file()


def test_legacy_and_external_lock_coexistence(tmp_path: Path) -> None:
    wf = build_initialized_workspace(tmp_path / "books" / "legacy-book")
    books_root = wf.root.parent
    slug = wf.root.name
    external_lock_path = books_root / ".orchestrator-locks" / f"{slug}.lock"
    legacy_lock_path = wf.root / "reports" / "runs" / ".orchestrator.lock"

    # Create the legacy lock file as if an older run left it
    legacy_lock_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_lock_path.write_text("pid=12345\n", encoding="utf-8")

    # If legacy lock is held by another process, start must be blocked
    foreign_legacy_lock = WorkspaceLock(legacy_lock_path)
    assert foreign_legacy_lock.acquire() is True

    orchestrator = BookOrchestrator(runner=MockRunner(), ops=WorkspaceOps())
    config = OrchestratorConfig(
        workspace_root=wf.root, start_at="export", stop_after="export"
    )
    outcome = orchestrator.start(config)

    assert outcome.status == "blocked"
    assert outcome.error_code == "workspace_locked"
    foreign_legacy_lock.release()

    # If external lock is held by another process, start must also be blocked
    foreign_ext_lock = WorkspaceLock(external_lock_path)
    assert foreign_ext_lock.acquire() is True

    outcome2 = orchestrator.start(config)
    assert outcome2.status == "blocked"
    assert outcome2.error_code == "workspace_locked"
    foreign_ext_lock.release()


def test_lock_released_on_paused_and_reacquired_on_resume(tmp_path: Path) -> None:
    wf = build_initialized_workspace(tmp_path / "books" / "paused-book")
    books_root = wf.root.parent
    slug = wf.root.name
    external_lock_path = books_root / ".orchestrator-locks" / f"{slug}.lock"

    ops = WorkspaceOps()
    # Stub crawl output
    for i, raw_p in enumerate(wf.raw_paths, start=1):
        raw_p.write_text(f"Raw body {i}\n" * 10, encoding="utf-8")
    from dich_truyen_agent.models import ApprovalScope, CrawlReport
    from dich_truyen_agent.storage import atomic_write_yaml

    rep = CrawlReport(
        discovered_count=len(wf.raw_paths),
        selected_count=len(wf.raw_paths),
        completed_count=len(wf.raw_paths),
        failed_count=0,
        max_chapters=0,
        scope=ApprovalScope.FULL,
        active_profile_source="shared",
        warnings=[],
    )
    atomic_write_yaml(wf.report, rep)

    ops.run_crawl = MagicMock(
        return_value=OperationResult(status=OperationStatus.OK, reason="ok")
    )

    orchestrator = BookOrchestrator(runner=MockRunner(), ops=ops)
    config = OrchestratorConfig(
        workspace_root=wf.root, start_at="crawl", stop_after="crawl", auto_approve=False
    )

    # First run without auto-approve pauses at crawl decision
    outcome = orchestrator.start(config)
    assert outcome.status == "paused"

    # Verify lock was released during pause: another lock instance can acquire it
    contending_lock = WorkspaceLock(external_lock_path)
    assert contending_lock.acquire() is True

    # If contending lock is held, resume fails with workspace_locked
    resume_blocked = orchestrator.resume(wf.root, decision="approve")
    assert resume_blocked.status == "blocked"
    assert resume_blocked.error_code == "workspace_locked"

    # Release contending lock; resume can now acquire and proceed
    contending_lock.release()
    resume_outcome = orchestrator.resume(wf.root, decision="approve")
    assert resume_outcome.status == "completed"
    # Resume executes and releases lock when done
    assert contending_lock.acquire() is True
    contending_lock.release()


def test_lock_released_on_blocked_and_exception(tmp_path: Path) -> None:
    wf = build_initialized_workspace(tmp_path / "books" / "blocked-book")
    books_root = wf.root.parent
    slug = wf.root.name
    external_lock_path = books_root / ".orchestrator-locks" / f"{slug}.lock"

    ops = WorkspaceOps()
    # Mock crawl failure causing status="blocked"
    ops.run_crawl = MagicMock(
        return_value=OperationResult(status=OperationStatus.BLOCKED, reason="failed")
    )

    orchestrator = BookOrchestrator(runner=MockRunner(), ops=ops)
    config = OrchestratorConfig(
        workspace_root=wf.root, start_at="crawl", stop_after="crawl"
    )

    outcome = orchestrator.start(config)
    assert outcome.status == "blocked"

    # Verify external lock is released
    check_lock = WorkspaceLock(external_lock_path)
    assert check_lock.acquire() is True
    check_lock.release()

    # Test release on unhandled exception during execution
    orchestrator._load_manifest = MagicMock(
        side_effect=RuntimeError("unexpected crash")
    )
    with pytest.raises(RuntimeError, match="unexpected crash"):
        orchestrator.start(config)

    # Verify external lock is released even after unhandled exception
    assert check_lock.acquire() is True
    check_lock.release()


def test_lock_released_on_completed(tmp_path: Path) -> None:
    wf = build_initialized_workspace(tmp_path / "books" / "completed-book")
    books_root = wf.root.parent
    slug = wf.root.name
    external_lock_path = books_root / ".orchestrator-locks" / f"{slug}.lock"

    ops = WorkspaceOps()
    for i, raw_p in enumerate(wf.raw_paths, start=1):
        raw_p.write_text(f"Raw body {i}\n" * 10, encoding="utf-8")
    from dich_truyen_agent.models import ApprovalScope, CrawlReport
    from dich_truyen_agent.storage import atomic_write_yaml

    rep = CrawlReport(
        discovered_count=len(wf.raw_paths),
        selected_count=len(wf.raw_paths),
        completed_count=len(wf.raw_paths),
        failed_count=0,
        max_chapters=0,
        scope=ApprovalScope.FULL,
        active_profile_source="shared",
        warnings=[],
    )
    atomic_write_yaml(wf.report, rep)
    ops.run_crawl = MagicMock(
        return_value=OperationResult(status=OperationStatus.OK, reason="ok")
    )

    orchestrator = BookOrchestrator(runner=MockRunner(), ops=ops)
    config = OrchestratorConfig(
        workspace_root=wf.root, start_at="crawl", stop_after="crawl", auto_approve=True
    )

    outcome = orchestrator.start(config)
    assert outcome.status == "completed"

    # Verify lock is released
    check_lock = WorkspaceLock(external_lock_path)
    assert check_lock.acquire() is True
    check_lock.release()


def test_pre_init_validation_failure_creates_no_partial_workspace(
    tmp_path: Path,
) -> None:
    books_root = tmp_path / "books"
    books_root.mkdir(parents=True, exist_ok=True)
    uninit_workspace = books_root / "uninitialized-book"

    orchestrator = BookOrchestrator(runner=MockRunner(), ops=WorkspaceOps())
    outcome = orchestrator.start(str(uninit_workspace))
    assert outcome.status == "blocked"
    assert outcome.exit_code == 3

    # Assert no workspace directory or partial files were created
    assert not uninit_workspace.exists()

    # Also test invalid slug escaping root
    invalid_workspace = books_root / ".."
    outcome2 = orchestrator.start(str(invalid_workspace))
    assert outcome2.status == "blocked"
    assert outcome2.exit_code == 3
