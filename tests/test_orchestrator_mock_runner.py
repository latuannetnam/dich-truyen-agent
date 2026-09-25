from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from dich_truyen_agent.orchestrator.runners.base import HarnessRunResult
from dich_truyen_agent.orchestrator.runners.mock import MockRunner


def test_mock_runner_records_calls_and_returns_default(tmp_path: Path) -> None:
    runner = MockRunner()
    events = []

    def on_event(ev: dict) -> None:
        events.append(ev)

    res = runner.run_phase(
        phase="translate",
        workspace=tmp_path,
        prompt="Translate Chapter 1",
        model="gemini-3.8-flash-high",
        timeout_seconds=900,
        on_event=on_event,
    )

    assert res.exit_code == 0
    assert res.timed_out is False
    assert len(runner.calls) == 1
    call = runner.calls[0]
    assert call.phase == "translate"
    assert call.workspace == tmp_path.resolve()
    assert call.prompt == "Translate Chapter 1"
    assert call.model == "gemini-3.8-flash-high"
    assert call.timeout_seconds == 900

    assert any(e.get("event") == "started" for e in events)
    assert any(e.get("event") == "finished" for e in events)


def test_mock_runner_returns_scripted_dict_outcomes(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    scripted_fail = HarnessRunResult(
        exit_code=1,
        timed_out=False,
        cancelled=False,
        started_at=now,
        ended_at=now,
        stdout_path=tmp_path / "stdout.log",
        stderr_path=tmp_path / "stderr.log",
        failure_detail="Scripted failure for metadata",
    )

    runner = MockRunner(scripted_outcomes={"metadata": scripted_fail})

    meta_res = runner.run_phase(
        phase="metadata",
        workspace=tmp_path,
        prompt="Translate metadata",
    )
    assert meta_res.exit_code == 1
    assert meta_res.failure_detail == "Scripted failure for metadata"

    # Other phases return default ok
    trans_res = runner.run_phase(
        phase="translate",
        workspace=tmp_path,
        prompt="Translate chapter 1",
    )
    assert trans_res.exit_code == 0


def test_mock_runner_executes_side_effects(tmp_path: Path) -> None:
    runner = MockRunner()

    target_file = tmp_path / "staging" / "translated.txt"

    def write_staged_file(workspace: Path, prompt: str, ctx: dict) -> None:
        target_file.parent.mkdir(parents=True, exist_ok=True)
        target_file.write_text("Staged Vietnamese Content", encoding="utf-8")

    runner.add_side_effect(write_staged_file)

    runner.run_phase(
        phase="translate",
        workspace=tmp_path,
        prompt="Translate chapter 1",
    )

    assert target_file.is_file()
    assert target_file.read_text(encoding="utf-8") == "Staged Vietnamese Content"
