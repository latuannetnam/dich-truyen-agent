"""Verify the oc-translator subagent has the right OpenCode frontmatter."""
import re
from pathlib import Path

import pytest

TRANSLATOR_MD = Path(__file__).parent.parent / ".opencode" / "agent" / "oc-translator.md"


@pytest.fixture(scope="module")
def frontmatter() -> str:
    assert TRANSLATOR_MD.is_file(), f"Missing {TRANSLATOR_MD}"
    content = TRANSLATOR_MD.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    assert match, f"No YAML frontmatter in {TRANSLATOR_MD}"
    return match.group(1)


def test_translator_md_exists():
    assert TRANSLATOR_MD.is_file(), f"Missing {TRANSLATOR_MD}"


def test_translator_mode_subagent(frontmatter):
    assert re.search(r"^mode:\s*subagent", frontmatter, re.MULTILINE), (
        "mode must be 'subagent'"
    )


def test_translator_hidden_true(frontmatter):
    assert re.search(r"^hidden:\s*true", frontmatter, re.MULTILINE), (
        "hidden must be true (invoke-only via task())"
    )


def test_translator_bash_tool_disabled(frontmatter):
    assert re.search(r"^  bash:\s*false", frontmatter, re.MULTILINE), (
        "tools.bash must be false"
    )


def test_translator_bash_permission_denied(frontmatter):
    assert re.search(r"^  bash:\s*deny", frontmatter, re.MULTILINE), (
        "permission.bash must be 'deny'"
    )


def test_translator_read_write_glob_grep_enabled(frontmatter):
    for tool in ("read", "write", "glob", "grep"):
        assert re.search(rf"^  {tool}:\s*true", frontmatter, re.MULTILINE), (
            f"tools.{tool} must be true"
        )
