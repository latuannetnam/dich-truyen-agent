from __future__ import annotations

from pathlib import Path
from typing import Any
import pytest

from dich_truyen_agent.models import (
    BookMetadata,
    BookState,
    StageStatus,
)
from dich_truyen_agent.orchestrator.graph import GraphRunner
from dich_truyen_agent.orchestrator.models import OrchestratorConfig
from dich_truyen_agent.orchestrator.runners.mock import MockRunner
from dich_truyen_agent.orchestrator.workspace_ops import WorkspaceOps
from dich_truyen_agent.storage import atomic_write_yaml, load_yaml_model
from orchestrator_support import (
    WorkspaceFixture,
    build_crawl_approved_workspace,
)


class TranslationGraphFixture:
    def __init__(self, tmp_path: Path, chapter_count: int = 2) -> None:
        self.wf: WorkspaceFixture = build_crawl_approved_workspace(tmp_path / "ws", chapter_count=chapter_count)
        self.ops = WorkspaceOps()
        self.runner = MockRunner()

        # Pre-populate translated metadata so translation-specific tests don't require metadata step
        meta = load_yaml_model(self.wf.book, BookMetadata)
        atomic_write_yaml(
            self.wf.book,
            meta.model_copy(
                update={
                    "translated_title": f"Dịch: {meta.title}",
                    "translated_author": f"Dịch: {meta.author}" if meta.author else None,
                }
            ),
        )

        # Helper side effect for valid chapter translation
        def default_translator_side_effect(workspace: Path, prompt: str, ctx: dict[str, Any]) -> None:
            if ctx.get("phase") == "chapter_translation":
                staged_txt = None
                for line in prompt.splitlines():
                    if "staged_txt:" in line:
                        staged_txt = Path(line.partition("staged_txt:")[2].strip())
                        break
                if staged_txt:
                    staged_txt.parent.mkdir(parents=True, exist_ok=True)
                    # Extract chapter id from staged filename
                    ch_num = int(staged_txt.name.split("-")[1])
                    content = (
                        f"# Chương {ch_num}: Tiêu đề chương {ch_num}\n\n"
                        f"Nội dung bản dịch chương {ch_num} đầy đủ và đạt chuẩn chất lượng.\n"
                    )
                    staged_txt.write_text(content, encoding="utf-8")

            elif ctx.get("phase") == "metadata_translation":
                book_path = workspace / "book.yaml"
                if book_path.is_file():
                    meta = load_yaml_model(book_path, BookMetadata)
                    updated = meta.model_copy(
                        update={
                            "translated_title": f"Dịch: {meta.title}",
                            "translated_author": f"Dịch: {meta.author}" if meta.author else None,
                        }
                    )
                    atomic_write_yaml(book_path, updated)

        self.runner.add_side_effect(default_translator_side_effect)

    def run(
        self,
        *,
        chapters: int = 2,
        batch_size: int = 5,
        start_at: str = "translate",
        stop_after: str = "translate",
        model: str | None = None,
        translation_model: str | None = None,
    ):
        config = OrchestratorConfig(
            workspace_root=self.wf.root,
            start_at=start_at,
            stop_after=stop_after,
            batch_size=batch_size,
            global_model=model,
            translation_model=translation_model,
        )
        runner = GraphRunner(self.ops, self.runner, config)
        self.active_runner = runner
        return runner.run()


@pytest.fixture
def translation_graph_fixture(tmp_path: Path) -> TranslationGraphFixture:
    return TranslationGraphFixture(tmp_path, chapter_count=2)


def test_two_chapters_use_two_fresh_agent_calls(translation_graph_fixture: TranslationGraphFixture) -> None:
    outcome = translation_graph_fixture.run(chapters=2, batch_size=2)
    assert outcome.status == "completed"
    assert [call.phase for call in translation_graph_fixture.runner.calls] == [
        "chapter_translation",
        "chapter_translation",
    ]

    # Verify both chapters are marked completed in state.yaml
    state = load_yaml_model(translation_graph_fixture.wf.root / "state.yaml", BookState)
    assert all(ch.translation.status is StageStatus.COMPLETED for ch in state.chapters)

    # Token protection: prompts must not contain raw or full translated chapter text
    for call in translation_graph_fixture.runner.calls:
        assert "Raw body" not in call.prompt
        assert "Nội dung bản dịch chương" not in call.prompt
        assert "raw_path:" in call.prompt
        assert "staged_txt:" in call.prompt


def test_metadata_translation_dispatches_when_missing_and_noops_when_present(tmp_path: Path) -> None:
    fix = TranslationGraphFixture(tmp_path, chapter_count=1)

    # Clear translated metadata in book.yaml
    book_path = fix.wf.root / "book.yaml"
    meta = load_yaml_model(book_path, BookMetadata)
    updated_meta = meta.model_copy(update={"translated_title": None, "translated_author": None})
    atomic_write_yaml(book_path, updated_meta)

    outcome = fix.run(chapters=1, batch_size=1)
    assert outcome.status == "completed"

    # Should have called metadata_translation then chapter_translation
    calls = [call.phase for call in fix.runner.calls]
    assert calls == ["metadata_translation", "chapter_translation"]

    # Verify metadata is now translated
    saved_meta = load_yaml_model(book_path, BookMetadata)
    assert saved_meta.translated_title is not None

    # Reset calls and run again - metadata translation should be a no-op!
    fix.runner.calls.clear()
    outcome2 = fix.run(chapters=1, batch_size=1)
    assert outcome2.status == "completed"
    assert len(fix.runner.calls) == 0  # No translation or metadata needed (already complete)


def test_distinct_attempt_staging_paths_on_retry(tmp_path: Path) -> None:
    fix = TranslationGraphFixture(tmp_path, chapter_count=1)
    fix.runner._side_effects.clear()

    attempt_count = 0

    def faulty_translator(workspace: Path, prompt: str, ctx: dict[str, Any]) -> None:
        nonlocal attempt_count
        if ctx.get("phase") == "chapter_translation":
            attempt_count += 1
            staged_txt = None
            for line in prompt.splitlines():
                if "staged_txt:" in line:
                    staged_txt = Path(line.partition("staged_txt:")[2].strip())
                    break
            if staged_txt:
                staged_txt.parent.mkdir(parents=True, exist_ok=True)
                if attempt_count == 1:
                    # Attempt 1 writes invalid / too short content
                    staged_txt.write_text("too short", encoding="utf-8")
                else:
                    # Attempt 2 writes valid content
                    staged_txt.write_text("# Chương 1: Tiêu đề hợp lệ\n\nNội dung chương dịch hợp lệ đầy đủ.\n", encoding="utf-8")

    fix.runner.add_side_effect(faulty_translator)

    outcome = fix.run(chapters=1, batch_size=1)
    assert outcome.status == "completed"
    assert attempt_count == 2
    assert len(fix.runner.calls) == 2
    # Verify staging paths in prompts are attempt-scoped
    assert "attempt-01" in fix.runner.calls[0].prompt
    assert "attempt-02" in fix.runner.calls[1].prompt


def test_unauthorized_workspace_mutation_by_translator_blocks(tmp_path: Path) -> None:
    fix = TranslationGraphFixture(tmp_path, chapter_count=1)
    fix.runner._side_effects.clear()

    def malicious_translator(workspace: Path, prompt: str, ctx: dict[str, Any]) -> None:
        if ctx.get("phase") == "chapter_translation":
            # Maliciously mutate book.yaml
            (workspace / "book.yaml").write_text("corrupted", encoding="utf-8")
            staged_txt = None
            for line in prompt.splitlines():
                if "staged_txt:" in line:
                    staged_txt = Path(line.partition("staged_txt:")[2].strip())
                    break
            if staged_txt:
                staged_txt.parent.mkdir(parents=True, exist_ok=True)
                staged_txt.write_text("# Chương 1: Tiêu đề\n\nNội dung dịch hợp lệ ở đây.\n", encoding="utf-8")

    fix.runner.add_side_effect(malicious_translator)

    outcome = fix.run(chapters=1, batch_size=1)
    assert outcome.status == "blocked"
    assert "unauthorized workspace mutation" in (outcome.error_message or "").lower()


def test_missing_or_gap_predecessor_translation_blocks_immediately(tmp_path: Path) -> None:
    fix = TranslationGraphFixture(tmp_path, chapter_count=2)

    # Invalidate Chapter 1 translation predecessor hash or file
    state_path = fix.wf.root / "state.yaml"
    state = load_yaml_model(state_path, BookState)
    # Simulate gap: Chapter 1 is pending, but someone tries to translate
    outcome = fix.run(chapters=2, batch_size=2)
    # Run should normally translate chapter 1 then chapter 2
    assert outcome.status == "completed"

    # Now mutate chapter 1 translated file to create hash mismatch
    ch1_txt = fix.wf.translation_paths[0]
    ch1_txt.write_text("corrupted previous translation", encoding="utf-8")

    # Invalidate chapter 2 translation in state to make it pending
    state = load_yaml_model(state_path, BookState)
    state.chapters[1].translation.status = StageStatus.PENDING
    atomic_write_yaml(state_path, state)

    fix.runner.calls.clear()
    outcome2 = fix.run(chapters=2, batch_size=2)
    assert outcome2.status == "blocked"
    assert len(fix.runner.calls) == 0  # No agent calls made!


def test_batch_size_looping_checkpoints_compactly(tmp_path: Path) -> None:
    fix = TranslationGraphFixture(tmp_path, chapter_count=2)
    outcome = fix.run(chapters=2, batch_size=1)
    assert outcome.status == "completed"
    assert len(fix.runner.calls) == 2
    assert [call.phase for call in fix.runner.calls] == [
        "chapter_translation",
        "chapter_translation",
    ]


def test_promotion_journal_recovery_on_resume(tmp_path: Path) -> None:
    from dich_truyen_agent.workspace import PromotionFailpoint, promote_chapter_translation

    fix = TranslationGraphFixture(tmp_path, chapter_count=2)

    # Stage chapter 1 manually
    run_staging = fix.wf.root / "reports" / "runs" / "test-run" / "staging"
    run_staging.mkdir(parents=True, exist_ok=True)
    staged_txt = run_staging / "chuong-0001-attempt-01-staged.txt"
    staged_txt.write_text("# Chương 1: Tiên Nhân Chỉ Lộ\n\nNội dung chương 1 hợp lệ.\n", encoding="utf-8")

    # Inject crash during chapter 1 promotion to create durable promotion journal
    try:
        PromotionFailpoint.set("after_canonical")
        promote_chapter_translation(fix.wf.root, 1, run_id="test-run", attempt=1)
    finally:
        PromotionFailpoint.set(None)

    journal_p = fix.wf.root / "reports" / "promotion-journal-1.yaml"
    assert journal_p.is_file()  # Journal was left on disk

    # Run translation graph: it must recover journal first and translate chapter 2
    outcome = fix.run(chapters=2, batch_size=2)
    assert outcome.status == "completed"
    # Chapter 1 was recovered without agent call, only Chapter 2 needed an agent call!
    assert len(fix.runner.calls) == 1
    assert "chapter 2" in fix.runner.calls[0].prompt.lower()
    # Journal was deleted after recovery
    assert not journal_p.is_file()


def test_model_override_honored_for_translation(tmp_path: Path) -> None:
    fix = TranslationGraphFixture(tmp_path, chapter_count=1)
    outcome = fix.run(chapters=1, batch_size=1, translation_model="gemini-3.8-flash-high")
    assert outcome.status == "completed"
    assert len(fix.runner.calls) == 1
    assert fix.runner.calls[0].model == "gemini-3.8-flash-high"

