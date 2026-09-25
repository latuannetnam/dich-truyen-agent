from __future__ import annotations

from pathlib import Path
import pytest
import yaml

from dich_truyen_agent.models import (
    OperationStatus,
    StageStatus,
)
from dich_truyen_agent.paths import workspace_paths
from dich_truyen_agent.storage import sha256_file
from dich_truyen_agent.workspace import (
    PromotionFailpoint,
    inspect_workspace,
    promote_chapter_translation,
    recover_chapter_promotion,
)
from orchestrator_support import (
    WorkspaceFixture,
    build_crawl_approved_workspace,
)


class FailpointController:
    def __init__(self, name: str):
        self.name = name

    def enable(self) -> None:
        PromotionFailpoint.set(self.name)

    def disable(self) -> None:
        PromotionFailpoint.set(None)


@pytest.fixture
def fail_after_glossary():
    controller = FailpointController("after_glossary")
    yield controller
    controller.disable()


@pytest.fixture
def fail_after_canonical():
    controller = FailpointController("after_canonical")
    yield controller
    controller.disable()


@pytest.fixture
def fail_after_state():
    controller = FailpointController("after_state")
    yield controller
    controller.disable()


@pytest.fixture
def workspace_with_staged_chapter(tmp_path: Path) -> WorkspaceFixture:
    wf = build_crawl_approved_workspace(tmp_path, chapter_count=2)
    run_staging = wf.root / "reports" / "runs" / "run-a" / "staging"
    run_staging.mkdir(parents=True, exist_ok=True)

    staged_txt = run_staging / "chuong-0001-attempt-01-staged.txt"
    staged_yaml = run_staging / "chuong-0001-attempt-01-proposals.yaml"

    staged_txt.write_text("# Chương 1 Tiên Nhân Chỉ Lộ\n\nNội dung chương 1 mượt mà.\n", encoding="utf-8")
    staged_yaml.write_text(
        yaml.safe_dump({"仙人": {"translation": "Tiên Nhân", "category": "character"}}),
        encoding="utf-8",
    )
    return wf


def test_recovery_is_idempotent(workspace_with_staged_chapter: WorkspaceFixture, fail_after_glossary: FailpointController) -> None:
    fail_after_glossary.enable()
    promote_chapter_translation(workspace_with_staged_chapter.root, 1, run_id="run-a", attempt=1)
    fail_after_glossary.disable()

    res1 = recover_chapter_promotion(workspace_with_staged_chapter.root, 1)
    assert res1.status is OperationStatus.OK

    res2 = recover_chapter_promotion(workspace_with_staged_chapter.root, 1)
    assert res2.status is OperationStatus.OK

    inspect_res = inspect_workspace(workspace_with_staged_chapter.root)
    assert inspect_res.status is OperationStatus.OK

    state = workspace_with_staged_chapter.reload_state()
    assert state.chapters[0].translation.status is StageStatus.COMPLETED
    assert state.chapters[0].translation.sha256 == sha256_file(workspace_with_staged_chapter.translation_paths[0])


def test_recovery_after_canonical_failpoint(workspace_with_staged_chapter: WorkspaceFixture, fail_after_canonical: FailpointController) -> None:
    fail_after_canonical.enable()
    promote_chapter_translation(workspace_with_staged_chapter.root, 1, run_id="run-a", attempt=1)
    fail_after_canonical.disable()

    # Canonical file was written, but glossary and state were not yet updated
    recover_res = recover_chapter_promotion(workspace_with_staged_chapter.root, 1)
    assert recover_res.status is OperationStatus.OK

    state = workspace_with_staged_chapter.reload_state()
    assert state.chapters[0].translation.status is StageStatus.COMPLETED

    paths = workspace_paths(workspace_with_staged_chapter.root.parent, workspace_with_staged_chapter.root.name)
    assert paths.glossary.is_file()


def test_recovery_blocks_on_divergent_file(workspace_with_staged_chapter: WorkspaceFixture, fail_after_glossary: FailpointController) -> None:
    fail_after_glossary.enable()
    promote_chapter_translation(workspace_with_staged_chapter.root, 1, run_id="run-a", attempt=1)
    fail_after_glossary.disable()

    # Mutate canonical translation file so its hash matches neither before nor after
    trans_file = workspace_with_staged_chapter.translation_paths[0]
    trans_file.write_text("Tampered content that diverges from journal!", encoding="utf-8")

    recover_res = recover_chapter_promotion(workspace_with_staged_chapter.root, 1)
    assert recover_res.status is OperationStatus.BLOCKED
    assert "diverged" in recover_res.reason.lower() or "blocked" in recover_res.reason.lower()


def test_recovery_after_state_failpoint(workspace_with_staged_chapter: WorkspaceFixture, fail_after_state: FailpointController) -> None:
    fail_after_state.enable()
    promote_chapter_translation(workspace_with_staged_chapter.root, 1, run_id="run-a", attempt=1)
    fail_after_state.disable()

    # All targets were written, but journal wasn't removed yet
    journal_file = workspace_with_staged_chapter.root / "reports" / "promotion-journal-1.yaml"
    assert journal_file.is_file()

    recover_res = recover_chapter_promotion(workspace_with_staged_chapter.root, 1)
    assert recover_res.status is OperationStatus.OK
    assert not journal_file.exists()

    state = workspace_with_staged_chapter.reload_state()
    assert state.chapters[0].translation.status is StageStatus.COMPLETED

