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
        ROOT / ".agent" / "skills" / "ag-crawl-book" / "SKILL.md",
        ROOT / ".claude" / "skills" / "cc-crawl-book" / "SKILL.md",
        ROOT / ".opencode" / "skill" / "oc-crawl-book" / "SKILL.md",
        ROOT / ".codex" / "skills" / "codex-crawl-book" / "SKILL.md",
        ROOT / ".agent" / "agents" / "ag_translator.md",
        ROOT / ".claude" / "agents" / "cc_translator.md",
        ROOT / ".opencode" / "agent" / "oc-translator.md",
        ROOT / ".codex" / "agents" / "codex_translator.md",
    ]
    for path in generated_paths:
        assert path.read_text(encoding="utf-8").startswith("---"), path


def test_opencode_translate_adapter_uses_embedded_loop_not_coordinator():
    text = (
        ROOT / ".opencode" / "skill" / "oc-translate-book" / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert "ag_coordinator" not in text
    assert "cc_coordinator" not in text
    assert "spawns a **Coordinator Subagent**" not in text


def test_generated_translate_adapters_use_compact_five_chapter_batches():
    generated_paths = [
        ROOT / ".agent" / "skills" / "ag-translate-book" / "SKILL.md",
        ROOT / ".claude" / "skills" / "cc-translate-book" / "SKILL.md",
        ROOT / ".opencode" / "skill" / "oc-translate-book" / "SKILL.md",
        ROOT / ".codex" / "skills" / "codex-translate-book" / "SKILL.md",
        ROOT / ".agent" / "agents" / "ag_coordinator.md",
        ROOT / ".claude" / "agents" / "cc_coordinator.md",
        ROOT / ".codex" / "agents" / "codex_coordinator.md",
    ]
    for path in generated_paths:
        text = path.read_text(encoding="utf-8")
        assert "next 20" not in text
        assert "next 5" in text or "5 chapters" in text or "5-chapter" in text
        assert "next-translation-work-item" in text
        assert "verify-staged-chapter" in text


def test_claude_translate_workflow_uses_compact_orchestration():
    text = (ROOT / ".claude" / "workflows" / "translate-book.js").read_text(
        encoding="utf-8"
    )
    assert "next-translation-work-item" in text
    assert "verify-staged-chapter" in text
    assert "const promoted = []" not in text
    assert "promoted.push" not in text
    assert "next 20" not in text
