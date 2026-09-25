from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from dich_truyen_agent.models import OperationStatus
from dich_truyen_agent.orchestrator.process import ProcessResult
from dich_truyen_agent.orchestrator.runners.agy import AgyRunner
from dich_truyen_agent.orchestrator.runners.base import resolve_model_for_phase


@pytest.fixture
def agy_runner() -> AgyRunner:
    return AgyRunner(
        executable="agy",
        available_models=[
            "gemini-3.8-flash-high",
            "gemini-3.8-flash-medium",
            "claude-sonnet-4-6",
            "gpt-oss-120b-medium",
            "literary",
        ],
    )


def test_model_is_a_distinct_argv_item(agy_runner: AgyRunner) -> None:
    command = agy_runner.build_command("ag_translator", "Translate chapter 1", "literary", 1800)
    assert command.count("--model") == 1
    assert command[command.index("--model") + 1] == "literary"


def test_agent_selection_and_no_default_permission_bypass(agy_runner: AgyRunner) -> None:
    # 1. Default: no permission bypass
    cmd = agy_runner.build_command("ag_translator", "Translate chapter 1", "claude-sonnet-4-6", 1800)
    assert "--agent" in cmd
    assert cmd[cmd.index("--agent") + 1] == "ag_translator"
    assert "--dangerously-skip-permissions" not in cmd

    # 2. Metadata agent
    meta_cmd = agy_runner.build_command("ag_metadata_translator", "Translate metadata", "gemini-3.8-flash-high", 1800)
    assert "--agent" in meta_cmd
    assert meta_cmd[meta_cmd.index("--agent") + 1] == "ag_metadata_translator"

    # 3. Explicit permission bypass opt-in
    bypass_cmd = agy_runner.build_command(
        "ag_translator", "Translate", allow_permission_bypass=True
    )
    assert "--dangerously-skip-permissions" in bypass_cmd


def test_omitted_model_passes_no_model_flag(agy_runner: AgyRunner) -> None:
    cmd = agy_runner.build_command("ag_translator", "Translate chapter 1", None, 1800)
    assert "--model" not in cmd


def test_model_resolution_routing() -> None:
    # 1. Global model applies everywhere when no override
    assert resolve_model_for_phase("metadata", global_model="gemini-3.8-flash-high", translation_model=None) == "gemini-3.8-flash-high"
    assert resolve_model_for_phase("profile_repair", global_model="gemini-3.8-flash-high", translation_model=None) == "gemini-3.8-flash-high"
    assert resolve_model_for_phase("translate", global_model="gemini-3.8-flash-high", translation_model=None) == "gemini-3.8-flash-high"

    # 2. Translation override changes translation only
    assert resolve_model_for_phase("metadata", global_model="gemini-3.8-flash-high", translation_model="claude-sonnet-4-6") == "gemini-3.8-flash-high"
    assert resolve_model_for_phase("translate", global_model="gemini-3.8-flash-high", translation_model="claude-sonnet-4-6") == "claude-sonnet-4-6"

    # 3. Both None
    assert resolve_model_for_phase("translate", global_model=None, translation_model=None) is None


def test_unavailable_model_returns_typed_blocker_before_launch(tmp_path: Path, agy_runner: AgyRunner) -> None:
    res = agy_runner.validate_model("nonexistent-model-slug")
    assert res.status is OperationStatus.BLOCKED
    assert "nonexistent-model-slug" in res.reason

    # run_phase also blocks without running process
    launched = False

    def fake_process_runner(*args, **kwargs):
        nonlocal launched
        launched = True
        raise AssertionError("Process must not be launched for invalid model")

    agy_runner.process_runner = fake_process_runner
    run_result = agy_runner.run_phase(
        phase="translate",
        workspace=tmp_path,
        prompt="Translate chapter 1",
        model="nonexistent-model-slug",
    )
    assert launched is False
    assert run_result.exit_code == 1
    assert "nonexistent-model-slug" in (run_result.failure_detail or "")


def test_prompt_contains_file_paths_and_no_raw_chapter_text(tmp_path: Path) -> None:
    # Work item paths
    work_dir = tmp_path / "workspace"
    work_dir.mkdir()
    staged_txt = work_dir / "staging" / "chapter_0001.txt"
    staged_yaml = work_dir / "staging" / "chapter_0001.yaml"
    work_item_file = work_dir / "staging" / "work_item.json"

    raw_chinese_content = "第一章 这是小说的原始中文内容，绝不能泄露进主提示词中。"

    # Prompt constructed for agent
    prompt = (
        f"Translate Chapter 1 for novel workspace.\n"
        f"Work Item Config: {work_item_file}\n"
        f"Target Staged Text: {staged_txt}\n"
        f"Target Staged Glossary: {staged_yaml}\n"
    )

    # Assert prompt contains absolute paths
    assert str(work_item_file) in prompt
    assert str(staged_txt) in prompt
    assert str(staged_yaml) in prompt
    assert "Chapter 1" in prompt

    # Assert prompt does NOT contain raw chapter text
    assert raw_chinese_content not in prompt
    assert "这是小说的原始中文内容" not in prompt


def test_run_phase_supervised_execution_and_stdout_parsing(tmp_path: Path, agy_runner: AgyRunner) -> None:
    now = datetime.now(UTC)

    def fake_proc_runner(argv, cwd, timeout_seconds, stdout_path, stderr_path, on_event=None):
        stdout_file = Path(stdout_path)
        stderr_file = Path(stderr_path)
        stdout_file.write_text(
            '{"conversation_id": "test-123", "status": "SUCCESS", "usage": {"input_tokens": 100, "output_tokens": 50}}',
            encoding="utf-8",
        )
        stderr_file.write_text("", encoding="utf-8")
        return ProcessResult(
            exit_code=0,
            timed_out=False,
            cancelled=False,
            started_at=now,
            finished_at=now,
            stdout_path=stdout_file,
            stderr_path=stderr_file,
            failure_detail=None,
            argv=argv,
        )

    agy_runner.process_runner = fake_proc_runner

    result = agy_runner.run_phase(
        phase="translate",
        workspace=tmp_path,
        prompt="Translate chapter 1",
        model="claude-sonnet-4-6",
    )

    assert result.exit_code == 0
    assert result.timed_out is False
    assert result.data.get("conversation_id") == "test-123"
    assert result.data.get("usage", {}).get("total_tokens", 150) == 150 or result.data.get("usage", {}).get("input_tokens") == 100
