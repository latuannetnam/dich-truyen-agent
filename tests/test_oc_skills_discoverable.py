"""Verify OpenCode-native skills are discoverable with valid frontmatter."""
from pathlib import Path
import re

import pytest

OC_SKILLS_DIR = Path(__file__).parent.parent / ".opencode" / "skill"

EXPECTED_SKILLS = [
    "oc-crawl-book",
    "oc-translate-book",
    "oc-check-translation",
    "oc-export-book",
]


def _parse_frontmatter(skill_md: Path) -> str:
    content = skill_md.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    assert match, f"No YAML frontmatter in {skill_md}"
    return match.group(1)


@pytest.mark.parametrize("skill_name", EXPECTED_SKILLS)
def test_skill_directory_exists(skill_name):
    skill_dir = OC_SKILLS_DIR / skill_name
    assert skill_dir.is_dir(), f"Missing skill directory: {skill_dir}"


@pytest.mark.parametrize("skill_name", EXPECTED_SKILLS)
def test_skill_md_exists(skill_name):
    skill_md = OC_SKILLS_DIR / skill_name / "SKILL.md"
    assert skill_md.is_file(), f"Missing SKILL.md: {skill_md}"


@pytest.mark.parametrize("skill_name", EXPECTED_SKILLS)
def test_skill_is_generated(skill_name):
    skill_md = OC_SKILLS_DIR / skill_name / "SKILL.md"
    assert "GENERATED from .harness/source" in skill_md.read_text(encoding="utf-8")


@pytest.mark.parametrize("skill_name", EXPECTED_SKILLS)
def test_skill_frontmatter_name_matches_folder(skill_name):
    skill_md = OC_SKILLS_DIR / skill_name / "SKILL.md"
    fm = _parse_frontmatter(skill_md)
    name_match = re.search(r"^name:\s*([\w-]+)", fm, re.MULTILINE)
    assert name_match, f"Missing 'name' in frontmatter of {skill_md}"
    assert name_match.group(1) == skill_name, (
        f"name '{name_match.group(1)}' does not match folder '{skill_name}'"
    )


@pytest.mark.parametrize("skill_name", EXPECTED_SKILLS)
def test_skill_frontmatter_description_uses_use_when(skill_name):
    skill_md = OC_SKILLS_DIR / skill_name / "SKILL.md"
    fm = _parse_frontmatter(skill_md)
    desc_match = re.search(r'^description:\s*["\']?(.+?)["\']?$', fm, re.MULTILINE)
    assert desc_match, f"Missing 'description' in frontmatter of {skill_md}"
    desc = desc_match.group(1).strip().strip("\"'")
    assert "Use when" in desc or "use when" in desc, (
        f"description should mention 'Use when' in {skill_md}, got: {desc!r}"
    )
