"""Verify the Cowork capability panel is rendered into both generated guides."""

from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent

COWORK_MARKERS = [
    "Claude Cowork Panel",
    "built on Claude Code",
    "cc-translate-book",
    "hooks do not fire",
]


@pytest.mark.parametrize("guide", [ROOT / "AGENTS.md", ROOT / "CLAUDE.md"])
def test_cowork_panel_present_in_guide(guide: Path):
    assert guide.is_file(), f"Missing {guide}"
    text = guide.read_text(encoding="utf-8")
    for marker in COWORK_MARKERS:
        assert marker in text, f"Missing {marker!r} in {guide.name}"


def test_no_cowork_adapter_tree_generated():
    # Cowork reuses cc-* adapters; no cw-* skills or cw_* agents should exist.
    assert not (ROOT / ".cowork").exists()
    for folder in [
        ROOT / ".claude" / "skills",
        ROOT / ".agent" / "skills",
        ROOT / ".codex" / "skills",
    ]:
        if not folder.exists():
            continue
        for child in folder.iterdir():
            assert not child.name.startswith("cw-"), child


def test_generated_cc_skills_map_to_orchestrator():
    orchestrate_skill = ROOT / ".claude" / "skills" / "cc-orchestrate-book" / "SKILL.md"
    assert orchestrate_skill.is_file(), f"Missing {orchestrate_skill}"
    text = orchestrate_skill.read_text(encoding="utf-8")
    assert "orchestrate" in text
    assert "--start-at" in text

    translate_skill = ROOT / ".claude" / "skills" / "cc-translate-book" / "SKILL.md"
    assert translate_skill.is_file(), f"Missing {translate_skill}"
    text = translate_skill.read_text(encoding="utf-8")
    assert "--start-at translate --stop-after translate" in text
