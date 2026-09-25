from __future__ import annotations

import json
from pathlib import Path
import uuid

import pytest

from dich_truyen_agent.orchestrator.models import OrchestratorConfig
from dich_truyen_agent.orchestrator.state import create_initial_state


@pytest.mark.parametrize(
    "start,stop",
    [
        ("crawl", "crawl"),
        ("crawl", "translate"),
        ("crawl", "qa"),
        ("crawl", "export"),
        ("translate", "translate"),
        ("translate", "qa"),
        ("translate", "export"),
        ("qa", "qa"),
        ("qa", "export"),
        ("export", "export"),
        ("auto", "crawl"),
        ("auto", "translate"),
        ("auto", "qa"),
        ("auto", "export"),
    ],
)
def test_valid_phase_spans(tmp_path: Path, start: str, stop: str) -> None:
    config = OrchestratorConfig(
        workspace_root=tmp_path,
        start_at=start,
        stop_after=stop,
    )
    assert config.start_at == start
    assert config.stop_after == stop


@pytest.mark.parametrize(
    "start,stop",
    [
        ("translate", "crawl"),
        ("qa", "crawl"),
        ("qa", "translate"),
        ("export", "crawl"),
        ("export", "translate"),
        ("export", "qa"),
    ],
)
def test_reversed_phase_spans_raise_validation_error(tmp_path: Path, start: str, stop: str) -> None:
    with pytest.raises(ValueError, match="cannot precede start_at"):
        OrchestratorConfig(
            workspace_root=tmp_path,
            start_at=start,
            stop_after=stop,
        )


def test_positive_integers_validation(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must be positive"):
        OrchestratorConfig(workspace_root=tmp_path, batch_size=0)

    with pytest.raises(ValueError, match="must be positive"):
        OrchestratorConfig(workspace_root=tmp_path, timeout_seconds=-5)


def test_default_formats_and_uuid_generation(tmp_path: Path) -> None:
    config = OrchestratorConfig(workspace_root=tmp_path)
    assert config.formats == ["epub", "txt"]
    # Check that run_id is a valid UUID
    parsed_uuid = uuid.UUID(config.run_id)
    assert parsed_uuid.version == 4

    # Invalid run_id raises
    with pytest.raises(ValueError, match="valid UUID string"):
        OrchestratorConfig(workspace_root=tmp_path, run_id="not-a-uuid")


def test_batch_size_resolution_precedence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 1. Explicit CLI override wins
    assert OrchestratorConfig.resolve_batch_size(explicit_batch_size=12) == 12

    # 2. Environment variable wins over .env and default
    monkeypatch.setenv("DICH_TRUYEN_TRANSLATION_BATCH_SIZE", "8")
    env_file = tmp_path / ".env"
    env_file.write_text("DICH_TRUYEN_TRANSLATION_BATCH_SIZE=3\n", encoding="utf-8")
    assert OrchestratorConfig.resolve_batch_size(explicit_batch_size=None, env_file=env_file) == 8

    # 3. .env file wins over default
    monkeypatch.delenv("DICH_TRUYEN_TRANSLATION_BATCH_SIZE", raising=False)
    assert OrchestratorConfig.resolve_batch_size(explicit_batch_size=None, env_file=env_file) == 3

    # 4. Default is 5
    empty_env = tmp_path / "empty.env"
    empty_env.write_text("", encoding="utf-8")
    assert OrchestratorConfig.resolve_batch_size(explicit_batch_size=None, env_file=empty_env) == 5


def test_state_creation_and_serialization(tmp_path: Path) -> None:
    config = OrchestratorConfig(
        workspace_root=tmp_path,
        start_at="translate",
        stop_after="qa",
    )
    run_dir = tmp_path / "reports" / "runs" / config.run_id
    state = create_initial_state(config, run_dir)

    assert state["run_id"] == config.run_id
    assert state["workspace_root"] == str(tmp_path.resolve())
    assert state["start_at"] == "translate"
    assert state["stop_after"] == "qa"
    assert state["batch_index"] == 0
    assert state["chapter_attempt"] == 0
    assert state["profile_repair_attempts"] == 0
    assert state["status"] == "running"

    # Verify state can be serialized to JSON without custom encoders
    serialized = json.dumps(state)
    deserialized = json.loads(serialized)
    assert deserialized["run_id"] == config.run_id
    # Assert no raw text or full chapter arrays exist in state
    assert "chapters" not in deserialized
    assert "raw" not in deserialized
    assert "content" not in deserialized
