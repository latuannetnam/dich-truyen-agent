"""Verify root guide files are generated from shared main-agent logic."""
from pathlib import Path

ROOT = Path(__file__).parent.parent


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_agents_md_is_generated_cross_harness_guide():
    text = read("AGENTS.md")
    assert "GENERATED from .harness/source" in text
    assert "Workspace Lifecycle" in text
    for skill in ["ag-crawl-book", "cc-crawl-book", "oc-crawl-book", "codex-crawl-book"]:
        assert skill in text


def test_claude_md_is_generated_claude_panel():
    text = read("CLAUDE.md")
    assert "GENERATED from .harness/source" in text
    assert "Workspace Lifecycle" in text
    assert "cc-crawl-book" in text
    assert "Bash" in text
    assert "Agent" in text


def test_guides_share_core_guardrails():
    agents = read("AGENTS.md")
    claude = read("CLAUDE.md")
    for phrase in [
        "Never read raw source Chinese files",
        "Chapters must be translated strictly in order",
        "External LLM API",
        "PYTHONUTF8=1",
    ]:
        assert phrase in agents
        assert phrase in claude
