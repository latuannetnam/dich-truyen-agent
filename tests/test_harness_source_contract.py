"""Verify the canonical harness source tree is complete."""

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
SOURCE = ROOT / ".harness" / "source"

EXPECTED_SKILLS = [
    "orchestrate-book",
    "crawl-book",
    "translate-book",
    "check-translation",
    "export-book",
]
EXPECTED_HARNESSES = ["ag", "cc", "oc", "codex"]
EXPECTED_AGENTS = ["translator", "metadata-translator"]
PANEL_MARKERS = {
    "ag": ["`ag-orchestrate-book`", "`ag-crawl-book`", "run_command", "view_file"],
    "cc": ["`cc-orchestrate-book`", "`cc-crawl-book`", "Bash", "Read"],
    "oc": ["`oc-orchestrate-book`", "`oc-crawl-book`", "bash", "read", "opencode.json"],
    "codex": ["`codex-orchestrate-book`", "`codex-crawl-book`", "shell_command"],
}


def read_json(path: Path) -> dict:
    assert path.is_file(), f"Missing {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def test_manifest_declares_all_harnesses_and_prefixes():
    manifest = read_json(SOURCE / "manifest.json")
    assert manifest["harnesses"] == EXPECTED_HARNESSES
    assert manifest["prefixes"] == {
        "ag": "ag",
        "cc": "cc",
        "oc": "oc",
        "codex": "codex",
    }
    assert manifest["skills"] == EXPECTED_SKILLS
    assert manifest["agents"] == EXPECTED_AGENTS
    assert manifest["opencode_extra_denied_skills"] == [
        "brainstorming",
        "writing-plans",
    ]
    assert "GENERATED from .harness/source" in manifest["generated_header"]


@pytest.mark.parametrize("skill", EXPECTED_SKILLS)
def test_shared_skill_source_exists(skill):
    path = SOURCE / "skills" / f"{skill}.md"
    assert path.is_file(), f"Missing shared skill source {path}"
    text = path.read_text(encoding="utf-8")
    assert "GENERATED" not in text
    assert "books/<book-slug>" in text
    assert "OpenCode" not in text
    assert "OpenCode-native" not in text
    assert "OpenCode Runtime" not in text
    assert "oc-check-translation" not in text
    assert "oc-" not in text


def test_translate_skill_maps_to_orchestrator():
    text = (SOURCE / "skills" / "translate-book.md").read_text(encoding="utf-8")
    assert "--start-at translate --stop-after translate" in text
    assert "next-translation-work-item" not in text
    assert "invoke_subagent" not in text


def test_orchestrate_skill_source_exists():
    path = SOURCE / "skills" / "orchestrate-book.md"
    assert path.is_file(), f"Missing {path}"
    text = path.read_text(encoding="utf-8")
    assert "--start-at" in text
    assert "--stop-after" in text
    assert "--auto-approve" in text
    assert "--resume" in text
    assert "0" in text and "2" in text and "3" in text and "1" in text


@pytest.mark.parametrize("agent", EXPECTED_AGENTS)
def test_agent_source_exists(agent):
    path = SOURCE / "agents" / f"{agent}.md"
    assert path.is_file(), f"Missing shared agent source {path}"
    text = path.read_text(encoding="utf-8")
    assert "external LLM" in text


def test_main_guide_source_exists():
    path = SOURCE / "guides" / "shared-main-agent.md"
    text = path.read_text(encoding="utf-8")
    assert "Workspace Lifecycle" in text
    assert "Token & Context Protection" in text


@pytest.mark.parametrize("harness", EXPECTED_HARNESSES)
def test_guide_panel_source_exists(harness):
    path = SOURCE / "guides" / "panels" / f"{harness}.md"
    assert path.is_file(), f"Missing guide panel {path}"
    text = path.read_text(encoding="utf-8")
    for marker in PANEL_MARKERS[harness]:
        assert marker in text


def test_guardrail_policy_source_exists():
    policy = read_json(SOURCE / "guardrails" / "external-llm-policy.json")
    assert "OPENAI_API_KEY" in policy["env_vars"]
    assert "api.openai.com" in policy["endpoints"]
    assert "openai" in policy["imports"]


def test_crawl_skill_describes_profile_driven_browser_settings() -> None:
    text = (ROOT / ".harness" / "source" / "skills" / "crawl-book.md").read_text(
        encoding="utf-8"
    )

    assert "browser:" in text
    assert "named browser strategy" in text
    assert "Do not hardcode site-specific browser behavior in `browser.py`" in text


def test_translator_prompt_has_emotional_craft_and_no_ascii_rule() -> None:
    text = (SOURCE / "agents" / "translator.md").read_text(encoding="utf-8")
    # New craft guidance present
    assert "Emotional fidelity" in text
    assert "Prose rhythm" in text
    assert "dialogue voice" in text.lower()
    # Register is generalized, no longer hardcoded archaic-only
    assert "register" in text.lower()
    # The harmful ASCII replacement table is gone
    assert "Lexical Sandbox" not in text
    assert "diacritic" in text.lower()
    # Isolation contract preserved
    assert "external LLM" in text
    assert "single chapter" in text.lower() or "Single chapter" in text


def test_setup_guide_describes_genre_profile_recommendation() -> None:
    text = (SOURCE / "guides" / "shared-main-agent.md").read_text(encoding="utf-8")
    assert "--style" in text
    assert "genre" in text.lower()
    assert "mat_the" in text
    assert "recommend" in text.lower()


def test_manifest_declares_cowork_guide_profile():
    manifest = read_json(SOURCE / "manifest.json")
    assert manifest.get("guide_profiles") == ["cw"]


def test_cowork_panel_source_exists():
    path = SOURCE / "guides" / "panels" / "cw.md"
    assert path.is_file(), f"Missing Cowork panel {path}"
    text = path.read_text(encoding="utf-8")
    for marker in [
        "Cowork",
        "built on Claude Code",
        "cc-orchestrate-book",
        "cc-translate-book",
        "hooks do not fire",
        "instruction level",
        "uv run --isolated",
    ]:
        assert marker in text, f"Missing marker {marker!r} in cw panel"


def test_architecture_documents_cowork_support():
    text = (ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")
    assert "ADR-0004" in text
    assert "ADR-0005" in text
    assert "Cowork" in text
    assert "v2.4" in text
    assert "guide_profiles" in text
    assert "general-purpose" in text
