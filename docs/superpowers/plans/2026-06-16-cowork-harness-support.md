# Claude Cowork Harness Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the translation pipeline runnable under Claude Cowork by reusing the existing `cc-*` adapters, hardening the external-LLM guardrail to be hook-independent, and rendering a guide-only Cowork capability panel.

**Architecture:** Cowork is built on Claude Code and reads the same `.claude/` plugin adapters, so no new prefixed adapter tree is generated. We add (1) an explicit external-LLM rule to the shared coordinator agent so the guardrail holds at instruction level when Cowork does not fire hooks, (2) a `guide_profiles` concept in the harness manifest/sync tool that renders a Cowork panel into `AGENTS.md` and `CLAUDE.md` without generating skills/agents, and (3) ADR-0004 + a v2.3 version bump.

**Tech Stack:** Python 3, `uv`, `pytest`, `ruff`. Generation driven by `tools/sync_harness_adapters.py` from `.harness/source/**`.

---

## Important conventions for the implementing engineer

- **Never edit generated adapter files directly** (anything containing the
  `GENERATED from .harness/source` header). Edit `.harness/source/**`, then
  regenerate with the sync tool.
- **Run every Python command with UTF-8 and a local uv cache** to avoid Windows
  encoding/cache errors. Prefix shell commands with:
  ```bash
  export PYTHONUTF8=1
  export UV_CACHE_DIR="$PWD/.uv-cache"
  ```
  (PowerShell equivalents: `$env:PYTHONUTF8=1`, `$env:UV_CACHE_DIR="$PWD\.uv-cache"`.)
- **Regeneration command** (used in several tasks):
  ```bash
  uv run python tools/sync_harness_adapters.py
  ```
- **Sync check command** (must return 0):
  ```bash
  uv run python tools/sync_harness_adapters.py --check
  ```
- The repo is a git worktree on branch `claude/modest-kare-e8120a`. Commit after
  each task.

---

## Task 1: Add the external-LLM guardrail rule to the shared coordinator agent

The coordinator is the only delegation worker whose source lacks an explicit
"no external LLM" rule. Cowork does not fire the `check_external_llm.py` hook, so
this rule must exist in instruction text. We tighten the contract test first.

**Files:**
- Modify: `tests/test_harness_source_contract.py:80-85`
- Modify: `.harness/source/agents/coordinator.md:4-8`
- Regenerated (do not hand-edit): `.agent/agents/ag_coordinator.md`,
  `.claude/agents/cc_coordinator.md`, `.codex/agents/codex_coordinator.md`

- [ ] **Step 1: Tighten the failing test**

In `tests/test_harness_source_contract.py`, replace the body of
`test_agent_source_exists` (currently lines 80-86) so the coordinator is no
longer exempt from the external-LLM requirement:

```python
@pytest.mark.parametrize("agent", ["translator", "metadata-translator", "coordinator"])
def test_agent_source_exists(agent):
    path = SOURCE / "agents" / f"{agent}.md"
    assert path.is_file(), f"Missing shared agent source {path}"
    text = path.read_text(encoding="utf-8")
    assert "external LLM" in text
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_harness_source_contract.py::test_agent_source_exists -v`
Expected: FAIL for the `coordinator` parametrization with an assertion error
(`assert "external LLM" in text`), the other two params PASS.

- [ ] **Step 3: Add the rule to the coordinator source**

In `.harness/source/agents/coordinator.md`, add a new operating rule under the
`## Operating Rules` list (after the existing rule 4 "Compact Output" line). The
list currently ends at:

```markdown
4. **Compact Output:** Never return a cumulative list of promoted chapters. Return only compact batch counters and boundary chapter IDs.
```

Add immediately after it:

```markdown
5. **No External LLM:** You never use an external LLM API, endpoint, SDK import, API key, curl request, or external script to translate. All translation happens only through the harness-native translator subagent you spawn for each chapter.
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_harness_source_contract.py::test_agent_source_exists -v`
Expected: PASS for all three parametrizations.

- [ ] **Step 5: Regenerate adapters and verify sync**

Run:
```bash
uv run python tools/sync_harness_adapters.py
uv run python tools/sync_harness_adapters.py --check
```
Expected: the first prints `rendered N generated adapters`; the second prints
`all generated adapters are current` and returns 0. The generated
`*_coordinator.md` files now contain the new rule 5.

- [ ] **Step 6: Commit**

```bash
git add tests/test_harness_source_contract.py .harness/source/agents/coordinator.md .agent/agents/ag_coordinator.md .claude/agents/cc_coordinator.md .codex/agents/codex_coordinator.md
git commit -m "feat: add explicit external-LLM prohibition to coordinator agent"
```

---

## Task 2: Add the Cowork panel source and manifest `guide_profiles` key

This task adds the canonical Cowork panel content and declares it in the
manifest. No tooling change yet — that is Task 3.

**Files:**
- Create: `.harness/source/guides/panels/cw.md`
- Modify: `.harness/source/manifest.json:1-13`
- Modify: `tests/test_harness_source_contract.py` (add two tests)

- [ ] **Step 1: Write the failing tests**

In `tests/test_harness_source_contract.py`, add these two tests at the end of the
file:

```python
def test_manifest_declares_cowork_guide_profile():
    manifest = read_json(SOURCE / "manifest.json")
    assert manifest.get("guide_profiles") == ["cw"]


def test_cowork_panel_source_exists():
    path = SOURCE / "guides" / "panels" / "cw.md"
    assert path.is_file(), f"Missing Cowork panel {path}"
    text = path.read_text(encoding="utf-8")
    for marker in [
        "Cowork",
        "built on Claude Code",
        "cc-translate-book",
        "hooks do not fire",
        "instruction level",
        "verify subagent dispatch",
    ]:
        assert marker in text, f"Missing marker {marker!r} in cw panel"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_harness_source_contract.py::test_manifest_declares_cowork_guide_profile tests/test_harness_source_contract.py::test_cowork_panel_source_exists -v`
Expected: both FAIL — the manifest has no `guide_profiles` key (returns `None`),
and `cw.md` does not exist.

- [ ] **Step 3: Create the Cowork panel source**

Create `.harness/source/guides/panels/cw.md` with exactly:

```markdown
### Claude Cowork Panel

- Claude Cowork is **built on Claude Code** and reads the same `.claude/` plugin adapters. Run the Claude Code pipeline skills directly: `cc-crawl-book`, `cc-translate-book`, `cc-check-translation`, and `cc-export-book`. There is no separate `cw-*` adapter set.
- Use `Bash` for CLI commands (`uv run python main.py ...`) and `Read` for bounded file inspection.
- Coordinator and translator delegation uses the same `cc_coordinator` and `cc_translator` `Agent` dispatch as Claude Code.
- **Cowork hooks do not fire.** The `check_external_llm.py` guardrail hook is inert under Cowork, so the external-LLM prohibition is enforced at **instruction level** inside the skills and agents instead. Do not rely on hook blocking in Cowork.
- **Verify subagent dispatch in Cowork before running large books.** Skill-body subagent dispatch is undocumented in Cowork; the token-protection model requires the translator subagent to be the only worker that reads raw chapter files. Confirm dispatch works on a small book first.
```

- [ ] **Step 4: Add `guide_profiles` to the manifest**

In `.harness/source/manifest.json`, add a `guide_profiles` key. The file becomes:

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
  "guide_profiles": ["cw"],
  "opencode_extra_denied_skills": ["brainstorming", "writing-plans"],
  "generated_header": "<!-- GENERATED from .harness/source by tools/sync_harness_adapters.py. Do not edit directly. -->"
}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_harness_source_contract.py::test_manifest_declares_cowork_guide_profile tests/test_harness_source_contract.py::test_cowork_panel_source_exists -v`
Expected: both PASS.

- [ ] **Step 6: Confirm the existing manifest test still passes**

Run: `uv run pytest tests/test_harness_source_contract.py::test_manifest_declares_all_harnesses_and_prefixes -v`
Expected: PASS (that test asserts individual keys, not exclusivity, so the new
key does not break it).

- [ ] **Step 7: Commit**

```bash
git add .harness/source/guides/panels/cw.md .harness/source/manifest.json tests/test_harness_source_contract.py
git commit -m "feat: add Cowork guide panel source and guide_profiles manifest key"
```

---

## Task 3: Render `guide_profiles` panels into AGENTS.md and CLAUDE.md

Now wire the sync tool so the Cowork panel appears in both generated guides
without generating any `cw-*` skill/agent files.

**Files:**
- Modify: `tools/sync_harness_adapters.py:235-258` (the `render_guides` function)
- Create: `tests/test_cowork_guide_panel.py`
- Regenerated (do not hand-edit): `AGENTS.md`, `CLAUDE.md`

- [ ] **Step 1: Write the failing test**

Create `tests/test_cowork_guide_panel.py` with:

```python
"""Verify the Cowork capability panel is rendered into both generated guides."""
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent

COWORK_MARKERS = [
    "Claude Cowork Panel",
    "built on Claude Code",
    "cc-translate-book",
    "hooks do not fire",
]


@pytest.mark.parametrize("guide", [ROOT / "AGENTS.md", ROOT / "CLAUDE.md"])
def test_cowork_panel_present_in_guide(guide: Path):
    assert guide.is_file(), f"Missing {guide}"
    text = guide.read_text(encoding="utf-8")
    for marker in COWORK_MARKERS:
        assert marker in text, f"Missing {marker!r} in {guide.name}"


def test_no_cowork_adapter_tree_generated():
    # Cowork reuses cc-* adapters; no cw-* skills or cw_* agents should exist.
    assert not (ROOT / ".cowork").exists()
    for folder in [
        ROOT / ".claude" / "skills",
        ROOT / ".agent" / "skills",
        ROOT / ".codex" / "skills",
    ]:
        for child in folder.iterdir():
            assert not child.name.startswith("cw-"), child
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_cowork_guide_panel.py -v`
Expected: `test_cowork_panel_present_in_guide` FAILS for both guides (the panel
is not rendered yet). `test_no_cowork_adapter_tree_generated` PASSES.

- [ ] **Step 3: Update `render_guides` in the sync tool**

In `tools/sync_harness_adapters.py`, replace the entire `render_guides`
function (currently lines 235-258) with:

```python
def render_guides(manifest: dict) -> list[RenderedFile]:
    shared = read_text(SOURCE / "guides" / "shared-main-agent.md").rstrip()
    panels = [
        read_text(SOURCE / "guides" / "panels" / f"{harness}.md").rstrip()
        for harness in manifest["harnesses"]
    ]
    profile_panels = [
        read_text(SOURCE / "guides" / "panels" / f"{profile}.md").rstrip()
        for profile in manifest.get("guide_profiles", [])
    ]
    agents = (
        generated_header(manifest)
        + shared
        + "\n\n## Harness Capability Matrix\n\n"
        + "\n\n".join(panels + profile_panels)
        + "\n"
    )
    claude_sections = [
        read_text(SOURCE / "guides" / "panels" / "cc.md").rstrip(),
        *profile_panels,
    ]
    claude = (
        generated_header(manifest)
        + shared
        + "\n\n## Claude Code Capability Panel\n\n"
        + "\n\n".join(claude_sections)
        + "\n"
    )
    return [
        RenderedFile(ROOT / "AGENTS.md", agents),
        RenderedFile(ROOT / "CLAUDE.md", claude),
    ]
```

- [ ] **Step 4: Regenerate the guides**

Run:
```bash
uv run python tools/sync_harness_adapters.py
```
Expected: prints `rendered N generated adapters`. `AGENTS.md` and `CLAUDE.md`
now end with the `### Claude Cowork Panel` section.

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run pytest tests/test_cowork_guide_panel.py -v`
Expected: all tests PASS.

- [ ] **Step 6: Verify the whole generated tree is in sync**

Run: `uv run python tools/sync_harness_adapters.py --check`
Expected: `all generated adapters are current`, return code 0.

- [ ] **Step 7: Commit**

```bash
git add tools/sync_harness_adapters.py tests/test_cowork_guide_panel.py AGENTS.md CLAUDE.md
git commit -m "feat: render Cowork capability panel into AGENTS.md and CLAUDE.md"
```

---

## Task 4: Document the decision in ARCHITECTURE.md (ADR-0004, v2.3)

**Files:**
- Modify: `ARCHITECTURE.md` (version banner ~line 13, "Current versions" list
  ~lines 19-35, "Harness Adapter Architecture" section ~lines 394-415, and the
  ADR section append after line 631)
- Modify: `tests/test_harness_source_contract.py` (add one doc test)

- [ ] **Step 1: Write the failing test**

In `tests/test_harness_source_contract.py`, add at the end of the file:

```python
def test_architecture_documents_cowork_support():
    text = (ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")
    assert "ADR-0004" in text
    assert "Cowork" in text
    assert "v2.3" in text
    assert "guide_profiles" in text
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_harness_source_contract.py::test_architecture_documents_cowork_support -v`
Expected: FAIL (none of the markers are present yet).

- [ ] **Step 3: Bump the architecture version banner**

In `ARCHITECTURE.md`, change line 13 from:

```markdown
This document describes **Translation Orchestration Architecture v2.2**.
```

to:

```markdown
This document describes **Translation Orchestration Architecture v2.3**.
```

- [ ] **Step 4: Add the v2.3 entry to the "Current versions" list**

In `ARCHITECTURE.md`, immediately after the `v2.2` bullet (which ends at the line
beginning `harmful ASCII diacritic-stripping rule is removed.`), add:

```markdown
- **v2.3 - Claude Cowork compatibility profile:** Cowork is treated as a
  Claude-Code-compatible runtime that reuses the generated `cc-*` adapters
  rather than a separate adapter tree. A `guide_profiles` manifest key renders a
  Cowork capability panel into `AGENTS.md` and `CLAUDE.md`, and the external-LLM
  guardrail is enforced at instruction level because Cowork does not fire hooks.
```

- [ ] **Step 5: Add a Cowork note to the Harness Adapter Architecture section**

In `ARCHITECTURE.md`, in the "## Harness Adapter Architecture" section, add a new
bullet to the existing bulleted list (after the bullet describing
`AGENTS.md`/`CLAUDE.md` generation, around line 409):

```markdown
- Claude Cowork reuses the generated `cc-*` skills and `cc_*` agents because it
  is built on Claude Code and reads the same `.claude/` adapters. It is declared
  as a `guide_profiles` entry (`cw`) so the sync tool renders a Cowork capability
  panel into `AGENTS.md` and `CLAUDE.md` without generating a duplicate `cw-*`
  adapter tree. Because Cowork does not fire hooks, the external-LLM guardrail is
  carried in skill/agent instruction text.
```

- [ ] **Step 6: Append ADR-0004**

In `ARCHITECTURE.md`, at the end of the "## Architecture Decision Records"
section (after the ADR-0003 "Verification" block, end of file), append:

```markdown
### ADR-0004: Claude Cowork Compatibility Profile

- **Status:** Accepted
- **Date:** 2026-06-16
- **Architecture version:** v2.3

#### Context

Claude Cowork is Anthropic's autonomous desktop agent. It is built on Claude
Code, shares the plugin model, and reads the same `.claude/` adapters. Two of its
properties matter here: it executes Bash CLI commands (so `main.py` orchestration
works), but it does **not** fire Claude Code hooks, so the `check_external_llm.py`
guardrail hook is inert under Cowork. Whether a skill body can dispatch a subagent
in Cowork is officially undocumented, though Cowork inherits Claude Code's `Agent`
dispatch.

#### Decision

Support Cowork as a Claude-Code-compatible profile that reuses the generated
`cc-*` adapters instead of generating a separate `cw-*` adapter tree:

- Add an explicit external-LLM prohibition rule to the shared coordinator agent
  so the guardrail holds at instruction level across the whole delegation chain
  when hooks do not fire. The other workers (translator, metadata-translator) and
  the `translate-book` skill already carry this text.
- Introduce a `guide_profiles` manifest key. The sync tool renders each profile
  panel into `AGENTS.md` and `CLAUDE.md` but does **not** generate skills or
  agents for it.
- Add a Cowork capability panel that points users at the `cc-*` skills and
  documents the hooks gap and the subagent-dispatch verification step.

A full `cw-*` adapter set was rejected: Cowork reads `.claude/`, not a `.cowork/`
directory, so a separate tree would be ignored, and placing `cw-*` files into
`.claude/` would cause duplicate skill discovery with `cc-*` in both Claude Code
and Cowork — which Cowork cannot suppress because it has no hooks/config
equivalent to `opencode.json`.

#### Consequences

- Cowork runs the pipeline through the existing `cc-*` adapters with no duplicate
  discovery and no divergent adapter tree to maintain.
- The external-LLM guardrail is now enforced at instruction level for every
  harness, hardening behavior beyond hook-based blocking.
- Large-book support in Cowork depends on subagent dispatch, which is
  undocumented; the panel instructs users to verify dispatch on a small book
  first. No code path assumes Cowork-specific dispatch behavior.
- Translator isolation, sequential ordering, staging, promotion, and glossary
  gates are unchanged.

#### Verification

- The coordinator agent source and generated coordinator adapters contain the
  external-LLM prohibition.
- The manifest declares `guide_profiles: ["cw"]` and the `cw` panel source exists
  with the documented markers.
- `AGENTS.md` and `CLAUDE.md` both contain the Cowork panel; no `cw-*` skill or
  `cw_*` agent files are generated.
- `tools/sync_harness_adapters.py --check` reports a clean tree.
```

- [ ] **Step 7: Run the test to verify it passes**

Run: `uv run pytest tests/test_harness_source_contract.py::test_architecture_documents_cowork_support -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add ARCHITECTURE.md tests/test_harness_source_contract.py
git commit -m "docs: document Cowork compatibility profile (ADR-0004, v2.3)"
```

---

## Task 5: Full verification sweep

**Files:** none (verification only)

- [ ] **Step 1: Regenerate and confirm a clean tree**

Run:
```bash
uv run python tools/sync_harness_adapters.py
uv run python tools/sync_harness_adapters.py --check
```
Expected: `all generated adapters are current`, return code 0. (If `--check`
reports stale files, a source edit was missed; regenerate and re-commit the
generated outputs.)

- [ ] **Step 2: Run the full test suite**

Run: `uv run pytest -q`
Expected: all tests pass (prior baseline was 311 passed, 1 skipped; this plan
adds tests, so the passed count increases). No failures.

- [ ] **Step 3: Run the linter**

Run: `uv run ruff check tools tests src main.py`
Expected: `All checks passed!`

- [ ] **Step 4: Final commit if anything regenerated**

If Step 1 regenerated any file not yet committed:
```bash
git add -A
git commit -m "chore: regenerate harness adapters for Cowork profile"
```
Otherwise skip. Confirm `git status` is clean.

---

## Self-review notes (for the implementer)

- **Spec coverage:** Task 1 = guardrail hardening; Task 2 = Cowork panel source +
  manifest; Task 3 = `render_guides` tooling + both guides; Task 4 = ADR-0004 +
  v2.3 docs; Task 5 = verification. All five spec change-sections are covered.
- **Out-of-scope item** (the stale "Lexical Sandbox" reference in
  `translate-book.md`) is intentionally **not** touched here.
- **Naming consistency:** the manifest key is `guide_profiles` and the profile id
  is `cw` everywhere; the panel file is `.harness/source/guides/panels/cw.md`;
  the generated guides are `AGENTS.md` and `CLAUDE.md`.
- **No new `cw-*` adapters** are produced — `render_all()` is not modified, so it
  still iterates only `manifest["harnesses"]`.
```
