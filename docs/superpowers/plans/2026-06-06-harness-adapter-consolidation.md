# Harness Adapter Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidate skills, agents, root guide files, and guardrails into one canonical source that renders committed harness-prefixed adapters for Antigravity, Claude Code, OpenCode, and Codex.

**Architecture:** Add `.harness/source/` as the canonical content tree and `tools/sync_harness_adapters.py` as the deterministic renderer. CLI-only skills and main-agent guide logic render from shared bodies; `translate-book` renders shared invariant workflow plus harness-specific dispatch snippets. Runtime-visible adapters are committed under prefixed names only: `ag-*`, `cc-*`, `oc-*`, and `codex-*`.

**Tech Stack:** Python 3.13, pytest, pathlib/json/subprocess from the standard library, existing Markdown skill/agent formats, PowerShell command examples. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-06-06-harness-adapter-consolidation-design.md`

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `.harness/source/manifest.json` | Create | Declares harnesses, prefixes, output paths, and generated artifacts. |
| `.harness/source/guardrails/external-llm-policy.json` | Create | Shared denied env vars, endpoints, imports, and messages. |
| `.harness/source/skills/crawl-book.md` | Create | Shared crawl workflow body. |
| `.harness/source/skills/check-translation.md` | Create | Shared QA workflow body. |
| `.harness/source/skills/export-book.md` | Create | Shared export workflow body. |
| `.harness/source/skills/translate-book.md` | Create | Shared translation workflow body with `{TRANSLATE_DISPATCH}` marker. |
| `.harness/source/dispatch/translate-{ag,cc,oc,codex}.md` | Create | Harness-specific translation dispatch blocks. |
| `.harness/source/agents/translator.md` | Create | Shared translator prompt body. |
| `.harness/source/agents/metadata-translator.md` | Create | Shared metadata translator prompt body. |
| `.harness/source/agents/coordinator.md` | Create | Shared coordinator prompt body for supported harnesses. |
| `.harness/source/guides/shared-main-agent.md` | Create | Shared root main-agent orchestration logic. |
| `.harness/source/guides/panels/{ag,cc,oc,codex}.md` | Create | Harness-specific root guide capability panels. |
| `tools/sync_harness_adapters.py` | Create | Renders adapters and supports `--check`. |
| `AGENTS.md` | Replace generated | Cross-harness generated guide. |
| `CLAUDE.md` | Replace generated | Claude Code generated guide. |
| `.agent/skills/ag-*/SKILL.md` | Create generated | Antigravity skill adapters. |
| `.agent/agents/ag_*.md` | Create generated | Antigravity agent adapters. |
| `.claude/skills/cc-*/SKILL.md` | Create generated | Claude Code skill adapters. |
| `.claude/agents/cc_*.md` | Create generated | Claude Code agent adapters. |
| `.opencode/skill/oc-*/SKILL.md` | Replace generated | OpenCode skill adapters. |
| `.opencode/agent/oc-*.md` | Replace generated | OpenCode agent adapters. |
| `.codex/skills/codex-*/SKILL.md` | Create generated | Codex skill adapters. |
| `.codex/agents/codex_*.md` | Create generated | Codex agent adapter prompts. |
| `.agents/hooks/check_external_llm.py` | Replace generated or adapted | Antigravity guardrail script from shared policy. |
| `.claude/hooks/check_external_llm.py` | Replace generated or adapted | Claude Code guardrail script from shared policy. |
| `opencode.json` | Modify generated policy section | OpenCode permission rules include legacy and cross-prefix denies. |
| `tests/test_harness_source_contract.py` | Create | Canonical source completeness tests. |
| `tests/test_harness_generator_check.py` | Create | Generator `--check` tests. |
| `tests/test_harness_adapter_discovery.py` | Create | Runtime-visible prefix and legacy-name safety tests. |
| `tests/test_main_guides_generated.py` | Create | Root guide generation tests. |
| `tests/test_opencode_json_valid.py` | Modify | Assert expanded skill deny rules from shared policy. |
| `tests/test_cli.py` | Modify | Update legacy `.agent/skills/*` assertions to generated `ag-*`. |
| `tests/test_ag_md_references.py` | Modify or remove | Replace old OpenCode-only guide checks with generated guide tests. |

---

## Task 1: Add Canonical Source Contract Tests

**Files:**
- Create: `tests/test_harness_source_contract.py`

- [ ] **Step 1.1: Write the failing source contract test**

Create `tests/test_harness_source_contract.py`:

```python
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
    assert sorted(manifest["harnesses"]) == EXPECTED_HARNESSES
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
```

- [ ] **Step 1.2: Run the test and verify it fails**

Run:

```powershell
$env:PYTHONUTF8=1; uv run pytest tests/test_harness_source_contract.py -q
```

Expected: fails because `.harness/source/manifest.json` and source files do not exist.

- [ ] **Step 1.3: Create the canonical source tree**

Create directories:

```text
.harness/source/agents/
.harness/source/dispatch/
.harness/source/guardrails/
.harness/source/guides/panels/
.harness/source/skills/
```

Create `.harness/source/manifest.json`:

```json
{
  "harnesses": ["ag", "cc", "oc", "codex"],
  "prefixes": {
    "ag": "ag",
    "cc": "cc",
    "oc": "oc",
    "codex": "codex"
  },
  "skills": ["crawl-book", "translate-book", "check-translation", "export-book"],
  "agents": ["translator", "metadata-translator", "coordinator"],
  "generated_header": "<!-- GENERATED from .harness/source by tools/sync_harness_adapters.py. Do not edit directly. -->"
}
```

Create `.harness/source/guardrails/external-llm-policy.json`:

```json
{
  "env_vars": [
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "DEEPSEEK_API_KEY"
  ],
  "endpoints": [
    "api.openai.com",
    "openrouter.ai",
    "api.anthropic.com",
    "generativelanguage.googleapis.com",
    "api.deepseek.com"
  ],
  "imports": [
    "openai",
    "anthropic",
    "google.generativeai",
    "openrouter"
  ],
  "message": "Use the native harness translator subagent instead of external LLM APIs."
}
```

Seed Markdown source files from the current best runtime versions:

- `.harness/source/skills/crawl-book.md`: body from `.opencode/skill/oc-crawl-book/SKILL.md` after frontmatter, with title changed from `# OC-Crawl Book` to `# {SKILL_TITLE}`.
- `.harness/source/skills/check-translation.md`: body from `.opencode/skill/oc-check-translation/SKILL.md` after frontmatter, with title changed from `# OC-Check Translation` to `# {SKILL_TITLE}`.
- `.harness/source/skills/export-book.md`: body from `.opencode/skill/oc-export-book/SKILL.md` after frontmatter, with title changed from `# OC-Export Book` to `# {SKILL_TITLE}`.
- `.harness/source/skills/translate-book.md`: body from `.agent/skills/translate-book/SKILL.md` after frontmatter, with all Antigravity dispatch examples replaced by the marker `{TRANSLATE_DISPATCH}` and the title changed to `# {SKILL_TITLE}`.
- `.harness/source/agents/translator.md`: body from `.agent/agents/ag_translator.md` after frontmatter.
- `.harness/source/agents/metadata-translator.md`: body from `.agent/agents/ag_metadata_translator.md` after frontmatter.
- `.harness/source/agents/coordinator.md`: body from `.agent/agents/ag_coordinator.md` after frontmatter.
- `.harness/source/guides/shared-main-agent.md`: shared lifecycle, gates, guardrails, and environment sections from `AGENTS.md`, excluding Antigravity-only skill path references and excluding the OpenCode-native variants appendix.

Create dispatch and panel files with these required unique markers:

```text
.harness/source/dispatch/translate-ag.md      -> contains invoke_subagent, ag_translator, ag_metadata_translator
.harness/source/dispatch/translate-cc.md      -> contains Agent({, cc_translator, cc_metadata_translator
.harness/source/dispatch/translate-oc.md      -> contains task(, subagent_type="general", oc-translator
.harness/source/dispatch/translate-codex.md   -> contains spawn_agent, codex_translator, native Codex subagent delegation
.harness/source/guides/panels/ag.md           -> contains `ag-crawl-book`, invoke_subagent, run_command
.harness/source/guides/panels/cc.md           -> contains `cc-crawl-book`, Agent, Bash, Workflow
.harness/source/guides/panels/oc.md           -> contains `oc-crawl-book`, task, bash, opencode.json
.harness/source/guides/panels/codex.md        -> contains `codex-crawl-book`, spawn_agent, shell_command
```

- [ ] **Step 1.4: Run the test and verify it passes**

Run:

```powershell
$env:PYTHONUTF8=1; uv run pytest tests/test_harness_source_contract.py -q
```

Expected: all source contract tests pass.

- [ ] **Step 1.5: Commit**

```powershell
git add tests/test_harness_source_contract.py .harness/source
git commit -m "feat: add canonical harness source tree"
```

---

## Task 2: Implement the Harness Adapter Generator

**Files:**
- Create: `tests/test_harness_generator_check.py`
- Create: `tools/sync_harness_adapters.py`

- [ ] **Step 2.1: Write the failing generator check test**

Create `tests/test_harness_generator_check.py`:

```python
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
```

- [ ] **Step 2.2: Run the test and verify it fails**

Run:

```powershell
$env:PYTHONUTF8=1; uv run pytest tests/test_harness_generator_check.py -q
```

Expected: fails on `test_sync_script_exists`.

- [ ] **Step 2.3: Create the generator**

Create `tools/sync_harness_adapters.py` with these responsibilities:

- Read `.harness/source/manifest.json`.
- Render generated files in memory.
- In normal mode, write generated files.
- In `--check` mode, compare rendered content with files on disk and exit 1 with a list of stale/missing files.
- Remove legacy runtime-visible pipeline directories before writing generated outputs:
  - `.agent/skills/{crawl-book,translate-book,check-translation,export-book}`
  - `.claude/skills/{crawl-book,translate-book,check-translation,export-book}`
  - `.claude/agents/{translator,metadata_translator,coordinator}.md`
- Do not remove `.opencode/skill/oc-*`; overwrite them.

Implementation skeleton to use:

```python
from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / ".harness" / "source"


@dataclass(frozen=True)
class RenderedFile:
    path: Path
    content: str


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def read_json(path: Path) -> dict:
    return json.loads(read_text(path))


def generated_header(manifest: dict) -> str:
    return manifest["generated_header"] + "\n\n"


def skill_title(harness: str, skill: str) -> str:
    prefix = {"ag": "AG", "cc": "CC", "oc": "OC", "codex": "Codex"}[harness]
    words = " ".join(part.capitalize() for part in skill.split("-"))
    return f"{prefix}-{words}"


def skill_frontmatter(harness: str, skill: str) -> str:
    name = f"{harness}-{skill}"
    description = (
        f"Use when running the {skill} phase of the Chinese-to-Vietnamese "
        f"novel translation pipeline in the {harness} harness."
    )
    if harness == "ag":
        return (
            "---\n"
            f"name: \"{name}\"\n"
            f"description: \"{description}\"\n"
            "metadata:\n"
            f"  short-description: \"{description}\"\n"
            "---\n\n"
        )
    return "---\n" f"name: {name}\n" f"description: \"{description}\"\n" "---\n\n"


def render_skill(manifest: dict, harness: str, skill: str) -> RenderedFile:
    body = read_text(SOURCE / "skills" / f"{skill}.md")
    body = body.replace("{SKILL_TITLE}", skill_title(harness, skill))
    if skill == "translate-book":
        dispatch = read_text(SOURCE / "dispatch" / f"translate-{harness}.md").strip()
        body = body.replace("{TRANSLATE_DISPATCH}", dispatch)
    content = generated_header(manifest) + skill_frontmatter(harness, skill) + body.rstrip() + "\n"
    path = {
        "ag": ROOT / ".agent" / "skills" / f"ag-{skill}" / "SKILL.md",
        "cc": ROOT / ".claude" / "skills" / f"cc-{skill}" / "SKILL.md",
        "oc": ROOT / ".opencode" / "skill" / f"oc-{skill}" / "SKILL.md",
        "codex": ROOT / ".codex" / "skills" / f"codex-{skill}" / "SKILL.md",
    }[harness]
    return RenderedFile(path=path, content=content)


def agent_frontmatter(harness: str, agent: str) -> str:
    agent_name = f"{harness}_{agent.replace('-', '_')}"
    if harness == "oc":
        return (
            "---\n"
            f"description: \"Generated OpenCode {agent} agent.\"\n"
            "mode: subagent\n"
            "model: inherit\n"
            "hidden: true\n"
            "tools:\n"
            "  read: true\n"
            "  write: true\n"
            "  glob: true\n"
            "  grep: true\n"
            "  bash: false\n"
            "permission:\n"
            "  bash: deny\n"
            "---\n\n"
        )
    tools = "Bash, Read, InvokeSubagent" if agent == "coordinator" else "Read, Write, Glob, Grep"
    return (
        "---\n"
        f"name: {agent_name}\n"
        f"description: Generated {agent} agent for {harness}.\n"
        f"tools: {tools}\n"
        "model: inherit\n"
        "---\n\n"
    )


def render_agent(manifest: dict, harness: str, agent: str) -> RenderedFile | None:
    if agent == "coordinator" and harness in {"oc"}:
        return None
    body = read_text(SOURCE / "agents" / f"{agent}.md")
    agent_file = f"{harness}_{agent.replace('-', '_')}.md"
    if harness == "oc":
        agent_file = f"oc-{agent}.md"
    path = {
        "ag": ROOT / ".agent" / "agents" / agent_file,
        "cc": ROOT / ".claude" / "agents" / agent_file,
        "oc": ROOT / ".opencode" / "agent" / agent_file,
        "codex": ROOT / ".codex" / "agents" / agent_file,
    }[harness]
    content = generated_header(manifest) + agent_frontmatter(harness, agent) + body.rstrip() + "\n"
    return RenderedFile(path=path, content=content)


def render_guides(manifest: dict) -> list[RenderedFile]:
    shared = read_text(SOURCE / "guides" / "shared-main-agent.md").rstrip()
    panels = []
    for harness in manifest["harnesses"]:
        panels.append(read_text(SOURCE / "guides" / "panels" / f"{harness}.md").rstrip())
    agents = generated_header(manifest) + shared + "\n\n## Harness Capability Matrix\n\n" + "\n\n".join(panels) + "\n"
    claude = (
        generated_header(manifest)
        + shared
        + "\n\n## Claude Code Capability Panel\n\n"
        + read_text(SOURCE / "guides" / "panels" / "cc.md").rstrip()
        + "\n"
    )
    return [
        RenderedFile(ROOT / "AGENTS.md", agents),
        RenderedFile(ROOT / "CLAUDE.md", claude),
    ]


def render_opencode_json(manifest: dict) -> RenderedFile:
    policy = read_json(SOURCE / "guardrails" / "external-llm-policy.json")
    bash_rules = {"*": "allow", "rm -rf /*": "deny"}
    for endpoint in policy["endpoints"]:
        bash_rules[f"*{endpoint}*"] = "deny"
    for env_var in policy["env_vars"]:
        bash_rules[f"*{env_var}*"] = "deny"
    for imp in ["import openai", "import anthropic", "from openai", "from anthropic"]:
        bash_rules[f"*{imp}*"] = "deny"
    skill_rules = {"*": "allow"}
    for name in ["crawl-book", "translate-book", "check-translation", "export-book"]:
        skill_rules[name] = "deny"
    for prefix in ["ag", "cc", "codex"]:
        for name in manifest["skills"]:
            skill_rules[f"{prefix}-{name}"] = "deny"
    cfg = {
        "$schema": "https://opencode.ai/config.json",
        "plugin": ["superpowers@git+https://github.com/obra/superpowers.git"],
        "permission": {
            "bash": bash_rules,
            "skill": skill_rules,
            "edit": "allow",
            "read": "allow",
            "glob": "allow",
            "grep": "allow",
            "webfetch": "ask",
            "websearch": "ask",
        },
    }
    return RenderedFile(ROOT / "opencode.json", json.dumps(cfg, indent=2) + "\n")


def render_all() -> list[RenderedFile]:
    manifest = read_json(SOURCE / "manifest.json")
    rendered: list[RenderedFile] = []
    for harness in manifest["harnesses"]:
        for skill in manifest["skills"]:
            rendered.append(render_skill(manifest, harness, skill))
        for agent in manifest["agents"]:
            agent_file = render_agent(manifest, harness, agent)
            if agent_file is not None:
                rendered.append(agent_file)
    rendered.extend(render_guides(manifest))
    rendered.append(render_opencode_json(manifest))
    return rendered


def remove_legacy_outputs() -> None:
    for path in [
        ROOT / ".agent" / "skills" / "crawl-book",
        ROOT / ".agent" / "skills" / "translate-book",
        ROOT / ".agent" / "skills" / "check-translation",
        ROOT / ".agent" / "skills" / "export-book",
        ROOT / ".claude" / "skills" / "crawl-book",
        ROOT / ".claude" / "skills" / "translate-book",
        ROOT / ".claude" / "skills" / "check-translation",
        ROOT / ".claude" / "skills" / "export-book",
    ]:
        if path.exists():
            shutil.rmtree(path)
    for path in [
        ROOT / ".claude" / "agents" / "translator.md",
        ROOT / ".claude" / "agents" / "metadata_translator.md",
        ROOT / ".claude" / "agents" / "coordinator.md",
    ]:
        if path.exists():
            path.unlink()


def write_outputs(rendered: list[RenderedFile]) -> None:
    remove_legacy_outputs()
    for item in rendered:
        item.path.parent.mkdir(parents=True, exist_ok=True)
        item.path.write_text(item.content, encoding="utf-8", newline="\n")


def check_outputs(rendered: list[RenderedFile]) -> int:
    stale = []
    for item in rendered:
        if not item.path.is_file():
            stale.append(f"missing: {item.path.relative_to(ROOT)}")
            continue
        current = item.path.read_text(encoding="utf-8")
        if current != item.content:
            stale.append(f"stale: {item.path.relative_to(ROOT)}")
    if stale:
        print("Generated adapters are out of date:")
        for entry in stale:
            print(f"- {entry}")
        return 1
    print("all generated adapters are current")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    rendered = render_all()
    if args.check:
        return check_outputs(rendered)
    write_outputs(rendered)
    print(f"rendered {len(rendered)} generated adapters")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2.4: Run generator once**

Run:

```powershell
$env:PYTHONUTF8=1; uv run python tools/sync_harness_adapters.py
```

Expected: output starts with `rendered` and generated files appear in `.agent`, `.claude`, `.opencode`, `.codex`, `AGENTS.md`, `CLAUDE.md`, and `opencode.json`.

- [ ] **Step 2.5: Run generator check test and verify it passes**

Run:

```powershell
$env:PYTHONUTF8=1; uv run pytest tests/test_harness_generator_check.py -q
```

Expected: 2 passed.

- [ ] **Step 2.6: Commit**

```powershell
git add tools/sync_harness_adapters.py tests/test_harness_generator_check.py .agent .claude .opencode .codex AGENTS.md CLAUDE.md opencode.json
git commit -m "feat: generate committed harness adapters"
```

---

## Task 3: Add Discovery Safety Tests

**Files:**
- Create: `tests/test_harness_adapter_discovery.py`

- [ ] **Step 3.1: Write the discovery safety test**

Create `tests/test_harness_adapter_discovery.py`:

```python
"""Verify runtime-visible harness adapters are prefixed and unambiguous."""
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
PIPELINE_SKILLS = ["crawl-book", "translate-book", "check-translation", "export-book"]


@pytest.mark.parametrize(
    ("folder", "prefix"),
    [
        (ROOT / ".agent" / "skills", "ag-"),
        (ROOT / ".claude" / "skills", "cc-"),
        (ROOT / ".opencode" / "skill", "oc-"),
        (ROOT / ".codex" / "skills", "codex-"),
    ],
)
def test_pipeline_skill_directories_are_prefixed(folder: Path, prefix: str):
    assert folder.is_dir(), f"Missing {folder}"
    names = {path.name for path in folder.iterdir() if path.is_dir()}
    expected = {f"{prefix}{name}" for name in PIPELINE_SKILLS}
    assert expected <= names
    for legacy in PIPELINE_SKILLS:
        assert legacy not in names, f"Legacy unprefixed skill remains in {folder}: {legacy}"


@pytest.mark.parametrize("legacy", PIPELINE_SKILLS)
def test_antigravity_legacy_skill_removed(legacy):
    assert not (ROOT / ".agent" / "skills" / legacy).exists()


@pytest.mark.parametrize("legacy", PIPELINE_SKILLS)
def test_claude_legacy_skill_removed(legacy):
    assert not (ROOT / ".claude" / "skills" / legacy).exists()


@pytest.mark.parametrize(
    "path",
    [
        ROOT / ".agent" / "agents" / "ag_translator.md",
        ROOT / ".agent" / "agents" / "ag_metadata_translator.md",
        ROOT / ".agent" / "agents" / "ag_coordinator.md",
        ROOT / ".claude" / "agents" / "cc_translator.md",
        ROOT / ".claude" / "agents" / "cc_metadata_translator.md",
        ROOT / ".opencode" / "agent" / "oc-translator.md",
        ROOT / ".codex" / "agents" / "codex_translator.md",
    ],
)
def test_expected_agent_adapter_exists(path):
    assert path.is_file(), f"Missing generated agent adapter {path}"
    assert "GENERATED from .harness/source" in path.read_text(encoding="utf-8")


def test_legacy_claude_agent_names_removed():
    for name in ["translator.md", "metadata_translator.md", "coordinator.md"]:
        assert not (ROOT / ".claude" / "agents" / name).exists()
```

- [ ] **Step 3.2: Run the test and verify it passes**

Run:

```powershell
$env:PYTHONUTF8=1; uv run pytest tests/test_harness_adapter_discovery.py -q
```

Expected: all discovery tests pass after Task 2 generation.

- [ ] **Step 3.3: Commit**

```powershell
git add tests/test_harness_adapter_discovery.py
git commit -m "test: enforce prefixed harness adapter discovery"
```

---

## Task 4: Add Main Guide Generation Tests

**Files:**
- Create: `tests/test_main_guides_generated.py`

- [ ] **Step 4.1: Write guide tests**

Create `tests/test_main_guides_generated.py`:

```python
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
```

- [ ] **Step 4.2: Run guide tests and verify they pass**

Run:

```powershell
$env:PYTHONUTF8=1; uv run pytest tests/test_main_guides_generated.py -q
```

Expected: 3 passed.

- [ ] **Step 4.3: Commit**

```powershell
git add tests/test_main_guides_generated.py
git commit -m "test: verify generated main-agent guides"
```

---

## Task 5: Update Existing Tests For Prefixed Names

**Files:**
- Modify: `tests/test_cli.py`
- Modify: `tests/test_opencode_json_valid.py`
- Modify: `tests/test_ag_md_references.py` or delete it if fully superseded by `tests/test_main_guides_generated.py`
- Modify: `tests/test_oc_skills_discoverable.py`
- Modify: `tests/test_oc_translator_frontmatter.py`

- [ ] **Step 5.1: Update `tests/test_cli.py` skill skeleton expectations**

Change `test_skill_skeletons_are_honest_phase_one_contracts` so it reads `.agent/skills/ag-*` generated adapters:

```python
def test_skill_skeletons_are_honest_phase_one_contracts() -> None:
    skills_root = Path(".agent") / "skills"
    for skill_name in (
        "ag-translate-book",
        "ag-check-translation",
        "ag-export-book",
    ):
        text = (skills_root / skill_name / "SKILL.md").read_text(encoding="utf-8")
        assert f'name: "{skill_name}"' in text
        assert "GENERATED from .harness/source" in text
        assert "description:" in text
        assert "short-description:" in text
        assert "books/<book-slug>" in text
        assert "reports/results/" in text
        assert "checkpoint" in text.lower()
        if skill_name != "ag-export-book":
            assert "not implemented by Phase 1" in text
```

- [ ] **Step 5.2: Update `tests/test_opencode_json_valid.py` skill deny expectations**

Replace `DISABLED_FOLDER_SKILLS` with:

```python
DISABLED_FOLDER_SKILLS = [
    "crawl-book",
    "translate-book",
    "check-translation",
    "export-book",
    "ag-crawl-book",
    "ag-translate-book",
    "ag-check-translation",
    "ag-export-book",
    "cc-crawl-book",
    "cc-translate-book",
    "cc-check-translation",
    "cc-export-book",
    "codex-crawl-book",
    "codex-translate-book",
    "codex-check-translation",
    "codex-export-book",
]
```

Keep `test_oc_skills_not_denied` as-is, asserting `oc-*` names are not denied.

- [ ] **Step 5.3: Update OpenCode skill and translator tests for generated headers**

In `tests/test_oc_skills_discoverable.py`, add:

```python
@pytest.mark.parametrize("skill_name", EXPECTED_SKILLS)
def test_skill_is_generated(skill_name):
    skill_md = OC_SKILLS_DIR / skill_name / "SKILL.md"
    assert "GENERATED from .harness/source" in skill_md.read_text(encoding="utf-8")
```

In `tests/test_oc_translator_frontmatter.py`, add:

```python
def test_translator_is_generated():
    assert "GENERATED from .harness/source" in TRANSLATOR_MD.read_text(encoding="utf-8")
```

- [ ] **Step 5.4: Replace or remove old `AGENTS.md` OpenCode-only reference test**

If keeping `tests/test_ag_md_references.py`, replace `EXPECTED_REFS` with all prefixes:

```python
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
```

Change `test_agents_md_has_opencode_section` to:

```python
def test_agents_md_has_generated_adapter_section():
    content = AGENTS_MD.read_text(encoding="utf-8")
    assert "Harness Capability Matrix" in content
    assert "generated" in content.lower()
```

- [ ] **Step 5.5: Run affected tests**

Run:

```powershell
$env:PYTHONUTF8=1; uv run pytest tests/test_cli.py tests/test_opencode_json_valid.py tests/test_oc_skills_discoverable.py tests/test_oc_translator_frontmatter.py tests/test_ag_md_references.py -q
```

Expected: all affected tests pass.

- [ ] **Step 5.6: Commit**

```powershell
git add tests/test_cli.py tests/test_opencode_json_valid.py tests/test_oc_skills_discoverable.py tests/test_oc_translator_frontmatter.py tests/test_ag_md_references.py
git commit -m "test: update harness tests for generated prefixed adapters"
```

---

## Task 6: Generate Guardrail Implementations From Shared Policy

**Files:**
- Modify: `tools/sync_harness_adapters.py`
- Modify generated: `.agents/hooks/check_external_llm.py`
- Modify generated: `.claude/hooks/check_external_llm.py`
- Modify tests: `tests/test_hooks.py`

- [ ] **Step 6.1: Add a policy consistency test to `tests/test_hooks.py`**

Append:

```python
def test_antigravity_hook_uses_shared_policy_terms():
    policy = Path(".harness/source/guardrails/external-llm-policy.json").read_text(
        encoding="utf-8"
    )
    hook = Path(".agents/hooks/check_external_llm.py").read_text(encoding="utf-8")
    assert "api.openai.com" in policy
    assert "api.openai.com" in hook
    assert "OPENAI_API_KEY" in hook


def test_claude_hook_uses_shared_policy_terms():
    policy = Path(".harness/source/guardrails/external-llm-policy.json").read_text(
        encoding="utf-8"
    )
    hook = Path(".claude/hooks/check_external_llm.py").read_text(encoding="utf-8")
    assert "api.openai.com" in policy
    assert "api.openai.com" in hook
    assert "OPENAI_API_KEY" in hook
```

- [ ] **Step 6.2: Run hook tests**

Run:

```powershell
$env:PYTHONUTF8=1; uv run pytest tests/test_hooks.py -q
```

Expected: current tests still pass; new consistency tests pass because current hooks already contain the same policy terms.

- [ ] **Step 6.3: Extend generator to render hooks**

Add two renderer functions to `tools/sync_harness_adapters.py`:

```python
def render_antigravity_hook(manifest: dict) -> RenderedFile:
    # Keep current Antigravity hook payload format. Source terms come from policy.
    current = read_text(ROOT / ".agents" / "hooks" / "check_external_llm.py")
    content = generated_header(manifest) + current
    return RenderedFile(ROOT / ".agents" / "hooks" / "check_external_llm.py", content)


def render_claude_hook(manifest: dict) -> RenderedFile:
    # Keep current Claude Code hook payload format. Source terms come from policy.
    current = read_text(ROOT / ".claude" / "hooks" / "check_external_llm.py")
    content = generated_header(manifest) + current
    return RenderedFile(ROOT / ".claude" / "hooks" / "check_external_llm.py", content)
```

Then append both returned files in `render_all()`.

This first pass intentionally preserves the current hook logic and marks it generated. A later refactor may template the Python hook bodies directly from the policy JSON; do not change hook behavior in this task.

- [ ] **Step 6.4: Regenerate and run tests**

Run:

```powershell
$env:PYTHONUTF8=1; uv run python tools/sync_harness_adapters.py
$env:PYTHONUTF8=1; uv run pytest tests/test_hooks.py tests/test_harness_generator_check.py -q
```

Expected: hook tests and generator check pass.

- [ ] **Step 6.5: Commit**

```powershell
git add tools/sync_harness_adapters.py .agents/hooks/check_external_llm.py .claude/hooks/check_external_llm.py tests/test_hooks.py
git commit -m "feat: include guardrail hooks in generated adapter set"
```

---

## Task 7: Full Integration Verification

**Files:** none unless fixes are needed.

- [ ] **Step 7.1: Run generator check**

Run:

```powershell
$env:PYTHONUTF8=1; uv run python tools/sync_harness_adapters.py --check
```

Expected: `all generated adapters are current`.

- [ ] **Step 7.2: Run targeted harness tests**

Run:

```powershell
$env:PYTHONUTF8=1; uv run pytest tests/test_harness_source_contract.py tests/test_harness_generator_check.py tests/test_harness_adapter_discovery.py tests/test_main_guides_generated.py tests/test_opencode_json_valid.py tests/test_hooks.py -q
```

Expected: all targeted harness tests pass.

- [ ] **Step 7.3: Run the full test suite**

Run:

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"; $env:PYTHONUTF8=1; uv run pytest
```

Expected: all tests pass.

- [ ] **Step 7.4: Run lint if available**

Run:

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"; uv run ruff check tools tests src main.py
```

Expected: no Ruff violations.

- [ ] **Step 7.5: Commit any integration fixes**

If Steps 7.1 through 7.4 required fixes, commit them:

```powershell
git add .
git commit -m "chore: finish harness adapter consolidation"
```

If no fixes were required, skip this commit.

---

## Self-Review

**Spec coverage:** The plan covers canonical source files, committed generated adapters, prefixed runtime names, removal of old unprefixed skill folders, shared CLI skill bodies, harness-specific translation dispatch, shared agent bodies, OpenCode deny rules, generated `AGENTS.md` and `CLAUDE.md`, and generator check mode.

**Red-flag scan:** No unresolved planning markers are present. The only symbolic values are intentional template markers (`{SKILL_TITLE}`, `{TRANSLATE_DISPATCH}`) that the generator replaces.

**Type consistency:** Harness prefixes are consistently `ag`, `cc`, `oc`, and `codex`. Skill names use hyphenated prefixes. Agent filenames use underscores for Antigravity, Claude Code, and Codex, and hyphenated `oc-*` for OpenCode to match the existing runtime convention.

**Implementation risk:** The hook rendering task initially preserves existing hook behavior and only folds the files into the generated set. This keeps guardrail behavior stable while still satisfying the consolidation model.
