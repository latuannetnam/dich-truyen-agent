"""Verify runtime-visible harness adapters are prefixed and unambiguous."""
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
PIPELINE_SKILLS = ["crawl-book", "translate-book", "check-translation", "export-book"]


@pytest.mark.parametrize(
    ("folder", "prefix"),
    [
        (ROOT / ".agent" / "skills", "ag-"),
        (ROOT / ".claude" / "skills", "cc-"),
        (ROOT / ".opencode" / "skill", "oc-"),
        (ROOT / ".codex" / "skills", "codex-"),
    ],
)
def test_pipeline_skill_directories_are_prefixed(folder: Path, prefix: str):
    assert folder.is_dir(), f"Missing {folder}"
    names = {path.name for path in folder.iterdir() if path.is_dir()}
    expected = {f"{prefix}{name}" for name in PIPELINE_SKILLS}
    assert expected <= names
    for legacy in PIPELINE_SKILLS:
        assert legacy not in names, f"Legacy unprefixed skill remains in {folder}: {legacy}"


@pytest.mark.parametrize("legacy", PIPELINE_SKILLS)
def test_antigravity_legacy_skill_removed(legacy):
    assert not (ROOT / ".agent" / "skills" / legacy).exists()


@pytest.mark.parametrize("legacy", PIPELINE_SKILLS)
def test_claude_legacy_skill_removed(legacy):
    assert not (ROOT / ".claude" / "skills" / legacy).exists()


@pytest.mark.parametrize(
    "path",
    [
        ROOT / ".agent" / "agents" / "ag_translator.md",
        ROOT / ".agent" / "agents" / "ag_metadata_translator.md",
        ROOT / ".agent" / "agents" / "ag_coordinator.md",
        ROOT / ".claude" / "agents" / "cc_translator.md",
        ROOT / ".claude" / "agents" / "cc_metadata_translator.md",
        ROOT / ".opencode" / "agent" / "oc-translator.md",
        ROOT / ".codex" / "agents" / "codex_translator.md",
    ],
)
def test_expected_agent_adapter_exists(path):
    assert path.is_file(), f"Missing generated agent adapter {path}"
    assert "GENERATED from .harness/source" in path.read_text(encoding="utf-8")


def test_legacy_claude_agent_names_removed():
    for name in ["translator.md", "metadata_translator.md", "coordinator.md"]:
        assert not (ROOT / ".claude" / "agents" / name).exists()
