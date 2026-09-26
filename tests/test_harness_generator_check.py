"""Verify generated harness adapters stay in sync with canonical sources."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
SYNC = ROOT / "tools" / "sync_harness_adapters.py"


def test_sync_script_exists():
    assert SYNC.is_file(), f"Missing {SYNC}"


def test_sync_check_mode_reports_clean_tree():
    result = subprocess.run(
        [sys.executable, str(SYNC), "--check"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    assert result.returncode == 0, result.stdout
    assert "all generated adapters are current" in result.stdout


def test_generated_skill_and_agent_frontmatter_starts_at_byte_zero():
    generated_paths = [
        ROOT / ".agent" / "skills" / "ag-orchestrate-book" / "SKILL.md",
        ROOT / ".agent" / "skills" / "ag-crawl-book" / "SKILL.md",
        ROOT / ".claude" / "skills" / "cc-orchestrate-book" / "SKILL.md",
        ROOT / ".claude" / "skills" / "cc-crawl-book" / "SKILL.md",
        ROOT / ".opencode" / "skill" / "oc-orchestrate-book" / "SKILL.md",
        ROOT / ".opencode" / "skill" / "oc-crawl-book" / "SKILL.md",
        ROOT / ".codex" / "skills" / "codex-orchestrate-book" / "SKILL.md",
        ROOT / ".codex" / "skills" / "codex-crawl-book" / "SKILL.md",
        ROOT / ".agent" / "agents" / "ag_translator.md",
        ROOT / ".agent" / "agents" / "ag_metadata_translator.md",
    ]
    for path in generated_paths:
        assert path.read_text(encoding="utf-8").startswith("---"), path


def test_opencode_translate_adapter_uses_embedded_loop_not_coordinator():
    text = (ROOT / ".opencode" / "skill" / "oc-translate-book" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "ag_coordinator" not in text
    assert "cc_coordinator" not in text
    assert "spawns a **Coordinator Subagent**" not in text


def test_generated_translate_adapters_map_to_orchestrator():
    generated_paths = [
        ROOT / ".agent" / "skills" / "ag-translate-book" / "SKILL.md",
        ROOT / ".claude" / "skills" / "cc-translate-book" / "SKILL.md",
        ROOT / ".opencode" / "skill" / "oc-translate-book" / "SKILL.md",
        ROOT / ".codex" / "skills" / "codex-translate-book" / "SKILL.md",
    ]
    for path in generated_paths:
        text = path.read_text(encoding="utf-8")
        assert "orchestrate" in text
        assert "--start-at translate --stop-after translate" in text
        assert "next-translation-work-item" not in text


def test_retired_claude_translate_workflow_removed():
    workflow = ROOT / ".claude" / "workflows" / "translate-book.js"
    assert not workflow.exists(), f"Retired workflow still exists: {workflow}"
