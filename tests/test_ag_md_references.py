"""Verify AGENTS.md references generated harness skill adapters."""
from pathlib import Path

import pytest

AGENTS_MD = Path(__file__).parent.parent / "AGENTS.md"

EXPECTED_REFS = [
    "ag-crawl-book",
    "ag-translate-book",
    "ag-check-translation",
    "ag-export-book",
    "cc-crawl-book",
    "cc-translate-book",
    "cc-check-translation",
    "cc-export-book",
    "oc-crawl-book",
    "oc-translate-book",
    "oc-check-translation",
    "oc-export-book",
    "codex-crawl-book",
    "codex-translate-book",
    "codex-check-translation",
    "codex-export-book",
]


def test_agents_md_exists():
    assert AGENTS_MD.is_file(), f"Missing {AGENTS_MD}"


def test_agents_md_has_generated_adapter_section():
    content = AGENTS_MD.read_text(encoding="utf-8")
    assert "Harness Capability Matrix" in content
    assert "generated" in content.lower()


@pytest.mark.parametrize("ref", EXPECTED_REFS)
def test_agents_md_references(ref):
    content = AGENTS_MD.read_text(encoding="utf-8")
    assert ref in content, f"AGENTS.md does not mention {ref!r}"
