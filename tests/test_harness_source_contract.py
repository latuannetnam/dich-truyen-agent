"""Verify the canonical harness source tree is complete."""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
SOURCE = ROOT / ".harness" / "source"

EXPECTED_SKILLS = [
    "crawl-book",
    "translate-book",
    "check-translation",
    "export-book",
]
EXPECTED_HARNESSES = ["ag", "cc", "oc", "codex"]
EXPECTED_AGENTS = ["translator", "metadata-translator", "coordinator"]
DISPATCH_MARKERS = {
    "ag": ["invoke_subagent", "ag_translator", "ag_metadata_translator"],
    "cc": ["Agent({", "cc_translator", "cc_metadata_translator"],
    "oc": ["task(", 'subagent_type="general"', "oc-translator"],
    "codex": [
        "spawn_agent",
        "codex_translator",
        "native Codex subagent delegation",
    ],
}
PANEL_MARKERS = {
    "ag": ["`ag-crawl-book`", "run_command", "view_file", "invoke_subagent"],
    "cc": ["`cc-crawl-book`", "Bash", "Read", "Agent", "Workflow"],
    "oc": ["`oc-crawl-book`", "bash", "read", "task", "opencode.json"],
    "codex": ["`codex-crawl-book`", "spawn_agent", "shell_command"],
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


@pytest.mark.parametrize("harness", EXPECTED_HARNESSES)
def test_translate_dispatch_source_exists(harness):
    path = SOURCE / "dispatch" / f"translate-{harness}.md"
    assert path.is_file(), f"Missing dispatch source {path}"
    text = path.read_text(encoding="utf-8")
    assert text.strip(), f"Empty dispatch source {path}"
    for marker in DISPATCH_MARKERS[harness]:
        assert marker in text


@pytest.mark.parametrize("agent", ["translator", "metadata-translator", "coordinator"])
def test_agent_source_exists(agent):
    path = SOURCE / "agents" / f"{agent}.md"
    assert path.is_file(), f"Missing shared agent source {path}"
    text = path.read_text(encoding="utf-8")
    assert "external LLM" in text or agent == "coordinator"


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
