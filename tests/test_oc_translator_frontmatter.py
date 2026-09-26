"""Verify translator subagent retirement and active agent frontmatter."""

import re
from pathlib import Path

import pytest

RETIRED_OC_TRANSLATOR = (
    Path(__file__).parent.parent / ".opencode" / "agent" / "oc-translator.md"
)
AG_TRANSLATOR = Path(__file__).parent.parent / ".agent" / "agents" / "ag_translator.md"


def test_oc_translator_retired():
    assert not RETIRED_OC_TRANSLATOR.exists(), (
        f"oc-translator.md should be retired, but was found at {RETIRED_OC_TRANSLATOR}"
    )


@pytest.fixture(scope="module")
def ag_frontmatter() -> str:
    assert AG_TRANSLATOR.is_file(), f"Missing {AG_TRANSLATOR}"
    content = AG_TRANSLATOR.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    assert match, f"No YAML frontmatter in {AG_TRANSLATOR}"
    return match.group(1)


def test_ag_translator_is_generated():
    assert "GENERATED from .harness/source" in AG_TRANSLATOR.read_text(encoding="utf-8")


def test_ag_translator_name(ag_frontmatter):
    assert re.search(r"^name:\s*ag_translator", ag_frontmatter, re.MULTILINE), (
        "name must be 'ag_translator'"
    )


def test_ag_translator_tools(ag_frontmatter):
    assert re.search(
        r"^tools:\s*Read, Write, Glob, Grep", ag_frontmatter, re.MULTILINE
    ), "tools must be 'Read, Write, Glob, Grep'"


def test_ag_translator_model(ag_frontmatter):
    assert re.search(r"^model:\s*inherit", ag_frontmatter, re.MULTILINE), (
        "model must be 'inherit'"
    )
