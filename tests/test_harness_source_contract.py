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


@pytest.mark.parametrize("skill", EXPECTED_SKILLS)
def test_shared_skill_source_exists(skill):
    path = SOURCE / "skills" / f"{skill}.md"
    assert path.is_file(), f"Missing shared skill source {path}"
    text = path.read_text(encoding="utf-8")
    assert "GENERATED" not in text
    assert "books/<book-slug>" in text


@pytest.mark.parametrize("harness", EXPECTED_HARNESSES)
def test_translate_dispatch_source_exists(harness):
    path = SOURCE / "dispatch" / f"translate-{harness}.md"
    assert path.is_file(), f"Missing dispatch source {path}"
    text = path.read_text(encoding="utf-8")
    assert text.strip(), f"Empty dispatch source {path}"


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
    assert f"`{harness}-" in path.read_text(encoding="utf-8")


def test_guardrail_policy_source_exists():
    policy = read_json(SOURCE / "guardrails" / "external-llm-policy.json")
    assert "OPENAI_API_KEY" in policy["env_vars"]
    assert "api.openai.com" in policy["endpoints"]
    assert "openai" in policy["imports"]
