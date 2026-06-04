"""Verify AGENTS.md references the OpenCode-native skills."""
from pathlib import Path

import pytest

AGENTS_MD = Path(__file__).parent.parent / "AGENTS.md"

EXPECTED_REFS = [
    "oc-crawl-book",
    "oc-translate-book",
    "oc-check-translation",
    "oc-export-book",
    "oc-translator",
]


def test_agents_md_exists():
    assert AGENTS_MD.is_file(), f"Missing {AGENTS_MD}"


def test_agents_md_has_opencode_section():
    content = AGENTS_MD.read_text(encoding="utf-8")
    assert "OpenCode-Native Skill Variants" in content, (
        "AGENTS.md is missing the 'OpenCode-Native Skill Variants' section"
    )


@pytest.mark.parametrize("ref", EXPECTED_REFS)
def test_agents_md_references(ref):
    content = AGENTS_MD.read_text(encoding="utf-8")
    assert ref in content, f"AGENTS.md does not mention {ref!r}"
