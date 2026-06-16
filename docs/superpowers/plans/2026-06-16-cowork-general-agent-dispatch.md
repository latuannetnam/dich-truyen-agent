# Cowork General-Agent Dispatch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the unworkable `cc_coordinator`/`cc_translator` delegation path in Claude Cowork with an OpenCode-style built-in general-agent dispatch, and correct the merged Cowork docs that over-promised custom-subagent delegation and the wrong CLI form.

**Architecture:** Cowork has no generated adapters — it reads the `cc-translate-book` skill, which embeds the coordinator orchestration Cowork cannot run (Cowork's `Agent` tool exposes only built-in agents). We add a **Cowork Fallback Dispatch** block to the cc dispatch source so the regenerated `cc-translate-book` skill carries an explicit alternate path: under Cowork the Main Agent runs the compact per-chapter loop itself (no coordinator tier) and dispatches a built-in `general-purpose` agent per chapter, instructing it to read and follow `.claude/agents/cc_translator.md`. This mirrors OpenCode (which has no coordinator) and preserves token protection because only the dispatched worker reads raw chapters. We also correct the CLI form for Cowork's Linux sandbox (`UV_CACHE_DIR=/tmp/uv-cache uv run --isolated --python 3.13 main.py ...`) and record the change as ADR-0005 (v2.4), superseding ADR-0004's delegation assumption.

**Tech Stack:** Python (pytest, ruff, `uv`), Markdown source-of-truth adapters under `.harness/source/**`, generated via `tools/sync_harness_adapters.py`.

---

## Background facts (verified this session)

- Cowork's `Agent` tool exposes **only built-in agents**; `cc_coordinator` / `cc_translator` / `cc_metadata_translator` are project-defined Claude Code agent types and are **not dispatchable** in Cowork.
- `uv run python main.py` **fails** in Cowork's Linux sandbox because the committed `.venv` is a Windows virtualenv. The working form is `UV_CACHE_DIR=/tmp/uv-cache uv run --isolated --python 3.13 main.py ...`.
- OpenCode precedent: [`.harness/source/dispatch/translate-oc.md`](.harness/source/dispatch/translate-oc.md) dispatches `subagent_type="general"` and tells it to use `oc-translator` instructions; `render_agent` returns `None` for `coordinator`+`oc` ([sync tool ~line 219](tools/sync_harness_adapters.py)). OpenCode runs the loop in the skill body, no coordinator tier.
- Generated `cc-translate-book` SKILL.md is built from `.harness/source/skills/translate-book.md` with `{TRANSLATE_DISPATCH}` ← `dispatch/translate-cc.md` and `{TRANSLATE_ORCHESTRATION}` ← `translate_orchestration("cc")` (Python). We only touch the dispatch source; the orchestration text is unchanged but is explicitly overridden by the fallback block for Cowork.

## File Structure

- Modify: `.harness/source/dispatch/translate-cc.md` — append the Cowork Fallback Dispatch block.
- Modify: `.harness/source/guides/panels/cw.md` — correct CLI form + dispatch reality, point to the fallback, keep hooks/external-LLM/verify caveats.
- Modify: `ARCHITECTURE.md` — bump to v2.4, add ADR-0005, mark ADR-0004 superseded-in-part.
- Modify: `tests/test_harness_source_contract.py` — update `cw` panel markers; add cc-dispatch Cowork markers; update architecture assertions to v2.4 / ADR-0005.
- Modify: `tests/test_cowork_guide_panel.py` — add a test asserting the **generated** `cc-translate-book` SKILL.md contains the Cowork fallback.
- Regenerate (no manual edit): all `cc-*`, `ag-*`, `oc-*`, `codex-*` adapters + `AGENTS.md` + `CLAUDE.md` via `tools/sync_harness_adapters.py`.

---

### Task 1: Tighten the contract tests for the corrected Cowork panel and cc dispatch

**Files:**
- Test: `tests/test_harness_source_contract.py`

- [ ] **Step 1: Update the `cw` panel markers and add cc-dispatch Cowork markers**

In `tests/test_harness_source_contract.py`, replace the marker list inside `test_cowork_panel_source_exists` so it asserts the corrected reality (drop the stale `"verify subagent dispatch"`, add the new facts):

```python
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
        "uv run --isolated",
        "not dispatchable",
        "general agent",
        "cc_translator.md",
        "general-agent dispatch",
    ]:
        assert marker in text, f"Missing marker {marker!r} in cw panel"
```

Then add a new test asserting the cc dispatch source carries the Cowork fallback:

```python
def test_cc_dispatch_documents_cowork_fallback():
    text = (SOURCE / "dispatch" / "translate-cc.md").read_text(encoding="utf-8")
    assert "Cowork Fallback Dispatch" in text
    assert "general-purpose" in text
    assert "cc_translator.md" in text
    assert "uv run --isolated" in text
    assert "no separate subagent tier" in text
```

- [ ] **Step 2: Update the architecture assertions to v2.4 / ADR-0005**

Replace `test_architecture_documents_cowork_support`:

```python
def test_architecture_documents_cowork_support():
    text = (ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")
    assert "ADR-0004" in text
    assert "ADR-0005" in text
    assert "Cowork" in text
    assert "v2.4" in text
    assert "guide_profiles" in text
    assert "general-purpose" in text
```

- [ ] **Step 3: Run the contract tests to verify they FAIL**

Run:
```bash
$env:UV_CACHE_DIR="$PWD/.uv-cache"; $env:PYTHONUTF8=1
uv run pytest tests/test_harness_source_contract.py -q
```
Expected: FAIL — `test_cowork_panel_source_exists` (new markers missing), `test_cc_dispatch_documents_cowork_fallback` (block not added yet), `test_architecture_documents_cowork_support` (ADR-0005/v2.4 missing).

- [ ] **Step 4: Commit the failing tests**

```bash
git add tests/test_harness_source_contract.py
git commit -m "test: assert Cowork general-agent dispatch in panel and cc dispatch source"
```

---

### Task 2: Add a test for the generated cc-translate-book Cowork fallback

**Files:**
- Test: `tests/test_cowork_guide_panel.py`

- [ ] **Step 1: Add a generated-skill assertion**

Append to `tests/test_cowork_guide_panel.py`:

```python
def test_generated_cc_translate_skill_has_cowork_fallback():
    skill = ROOT / ".claude" / "skills" / "cc-translate-book" / "SKILL.md"
    assert skill.is_file(), f"Missing {skill}"
    text = skill.read_text(encoding="utf-8")
    assert "Cowork Fallback Dispatch" in text
    assert "general-purpose" in text
    assert ".claude/agents/cc_translator.md" in text
```

- [ ] **Step 2: Run to verify it FAILS**

Run:
```bash
$env:UV_CACHE_DIR="$PWD/.uv-cache"; $env:PYTHONUTF8=1
uv run pytest tests/test_cowork_guide_panel.py::test_generated_cc_translate_skill_has_cowork_fallback -q
```
Expected: FAIL — generated skill does not yet contain the fallback (regeneration happens in Task 5).

- [ ] **Step 3: Commit**

```bash
git add tests/test_cowork_guide_panel.py
git commit -m "test: assert generated cc-translate-book carries Cowork fallback dispatch"
```

---

### Task 3: Add the Cowork Fallback Dispatch block to the cc dispatch source

**Files:**
- Modify: `.harness/source/dispatch/translate-cc.md`

- [ ] **Step 1: Append the fallback block**

Append the following to the end of `.harness/source/dispatch/translate-cc.md` (after the existing coordinator dispatch block):

```markdown

### Cowork Fallback Dispatch (built-in general agent)

Claude Cowork reads these same `cc-*` adapters, but its `Agent` tool exposes only
built-in agents — `cc_coordinator`, `cc_translator`, and `cc_metadata_translator`
are **not dispatchable** there — and Cowork's Linux sandbox cannot use the
committed Windows `.venv`. When you are running under Cowork:

- Run every CLI command as
  `UV_CACHE_DIR=/tmp/uv-cache uv run --isolated --python 3.13 main.py <command>`
  instead of the `python main.py` form.
- Do **not** spawn a Coordinator Subagent and do **not** follow the Coordinator
  micro-loop below. The **Main Agent itself** runs the compact per-chapter loop
  (fetch `next-translation-work-item` -> dispatch one translator worker ->
  `verify-staged-chapter` -> `promote-chapter`), repeating up to the effective
  `batch_size`. This is the Coordinator's job done inline, with **no separate subagent tier**.
- For each chapter, dispatch the built-in general agent as the translator worker:
  ```text
  Agent({
    subagent_type: "general-purpose",
    prompt: "Read and follow .claude/agents/cc_translator.md exactly. Translate the assigned chapter using the absolute paths reported by next-translation-work-item, including glossary_context_path. Return only the translator's compact JSON result."
  })
  ```
- For metadata translation (skill Step 1.5), dispatch the built-in general agent
  instructed to read and follow `.claude/agents/cc_metadata_translator.md`.
- The Main Agent must still never read raw Chinese or completed Vietnamese
  chapters; the dispatched general worker is the only reader of raw chapter files.
  This preserves the token-protection model without the custom coordinator and
  translator agents.
```

- [ ] **Step 2: Verify the marker test now passes at source level**

Run:
```bash
$env:UV_CACHE_DIR="$PWD/.uv-cache"; $env:PYTHONUTF8=1
uv run pytest tests/test_harness_source_contract.py::test_cc_dispatch_documents_cowork_fallback tests/test_harness_source_contract.py::test_translate_dispatch_source_exists -q
```
Expected: PASS (the existing `cc` markers `Agent({`, `cc_translator`, `cc_metadata_translator` still present; new fallback markers present).

- [ ] **Step 3: Commit**

```bash
git add .harness/source/dispatch/translate-cc.md
git commit -m "feat: add Cowork built-in general-agent fallback to cc translate dispatch"
```

---

### Task 4: Correct the Cowork capability panel source

**Files:**
- Modify: `.harness/source/guides/panels/cw.md`

- [ ] **Step 1: Replace the panel body**

Overwrite `.harness/source/guides/panels/cw.md` with:

```markdown
### Claude Cowork Panel

- Claude Cowork is **built on Claude Code** and reads the same `.claude/` plugin adapters. Run the Claude Code pipeline skills directly: `cc-crawl-book`, `cc-translate-book`, `cc-check-translation`, and `cc-export-book`. There is no separate `cw-*` adapter set.
- **CLI form under Cowork's Linux sandbox.** The committed `.venv` is a Windows virtualenv and is unusable in Cowork's Linux sandbox. Run every CLI command in an isolated, ephemeral environment: `UV_CACHE_DIR=/tmp/uv-cache uv run --isolated --python 3.13 main.py <command>`. The Windows `$env:PYTHONUTF8=1; uv run python main.py ...` form applies only when running on Windows.
- **Custom subagents are not dispatchable in Cowork.** Cowork's `Agent` tool exposes only built-in agents, so the `cc_coordinator` / `cc_translator` / `cc_metadata_translator` dispatch that Claude Code uses does **not** work here. Use the **Cowork Fallback Dispatch** documented in the `cc-translate-book` skill: the Main Agent runs the compact per-chapter loop itself (no Coordinator tier) and dispatches a built-in **general agent** for each chapter, instructing it to read and follow `.claude/agents/cc_translator.md` against the `next-translation-work-item` paths. Metadata translation dispatches a general agent that follows `.claude/agents/cc_metadata_translator.md`.
- **Token protection still holds.** The Main Agent handles only CLI JSON and dispatch; the dispatched general worker is the only worker that reads raw chapter files, in its own isolated context. Never read raw Chinese or completed Vietnamese chapters into the Main Agent session.
- **Cowork hooks do not fire.** The `check_external_llm.py` guardrail hook is inert under Cowork, so the external-LLM prohibition is enforced at **instruction level** inside the skills and agents. Never use an external LLM API to translate, regardless of hook state.
- **Verify the general-agent dispatch on a small book first.** Before running large books, confirm the built-in general worker correctly reads and applies the `cc_translator` instructions in your Cowork build.
```

- [ ] **Step 2: Verify the panel marker test passes at source level**

Run:
```bash
$env:UV_CACHE_DIR="$PWD/.uv-cache"; $env:PYTHONUTF8=1
uv run pytest tests/test_harness_source_contract.py::test_cowork_panel_source_exists -q
```
Expected: PASS — all markers (`uv run --isolated`, `not dispatchable`, `general agent`, `cc_translator.md`, `verify the general-agent dispatch`, plus retained `built on Claude Code`, `hooks do not fire`, `instruction level`) present.

- [ ] **Step 3: Commit**

```bash
git add .harness/source/guides/panels/cw.md
git commit -m "fix: correct Cowork panel for general-agent dispatch and isolated-venv CLI"
```

---

### Task 5: Regenerate adapters and verify generated tree

**Files:**
- Regenerate (tool-owned): `.claude/skills/cc-translate-book/SKILL.md`, all other prefixed adapters, `AGENTS.md`, `CLAUDE.md`.

- [ ] **Step 1: Regenerate**

Run:
```bash
$env:UV_CACHE_DIR="$PWD/.uv-cache"; $env:PYTHONUTF8=1
uv run python tools/sync_harness_adapters.py
```
Expected: writes updated files; reports the regenerated count.

- [ ] **Step 2: Verify the generated skill carries the fallback**

Run:
```bash
$env:UV_CACHE_DIR="$PWD/.uv-cache"; $env:PYTHONUTF8=1
uv run pytest tests/test_cowork_guide_panel.py -q
```
Expected: PASS — including `test_generated_cc_translate_skill_has_cowork_fallback`.

- [ ] **Step 3: Verify the sync tree is clean**

Run:
```bash
$env:UV_CACHE_DIR="$PWD/.uv-cache"; $env:PYTHONUTF8=1
uv run python tools/sync_harness_adapters.py --check
```
Expected: clean tree (no diff).

- [ ] **Step 4: Commit the regenerated adapters**

```bash
git add .claude .agent .opencode .codex AGENTS.md CLAUDE.md
git commit -m "chore: regenerate adapters with Cowork general-agent fallback dispatch"
```

---

### Task 6: Record ADR-0005 and bump architecture to v2.4

**Files:**
- Modify: `ARCHITECTURE.md` (line 13 banner; Current versions list ~line 36; ADR-0004 status note ~line 645; append ADR-0005)

- [ ] **Step 1: Bump the version banner**

Change line 13 from:
```
This document describes **Translation Orchestration Architecture v2.3**.
```
to:
```
This document describes **Translation Orchestration Architecture v2.4**.
```

- [ ] **Step 2: Add a v2.4 entry to the Current versions list**

Immediately above the existing `- **v2.3 - Claude Cowork compatibility profile:**` bullet (~line 36), insert:
```
- **v2.4 - Cowork general-agent dispatch:** Cowork cannot dispatch the custom
  `cc_*` subagents, so the `cc-translate-book` skill carries a Cowork fallback that
  runs the compact loop in the Main Agent and dispatches a built-in
  `general-purpose` worker per chapter (mirroring OpenCode). The Cowork CLI form
  uses an isolated ephemeral venv. See ADR-0005.
```

- [ ] **Step 3: Mark ADR-0004 superseded in part**

Change the ADR-0004 `Status` line (~line 647) from:
```
- **Status:** Accepted
```
to:
```
- **Status:** Accepted; delegation assumption superseded by ADR-0005
```

- [ ] **Step 4: Append ADR-0005**

After the ADR-0004 `#### Verification` block (after line 703), append:

```markdown

### ADR-0005: Cowork General-Agent Dispatch

- **Status:** Accepted
- **Date:** 2026-06-16
- **Architecture version:** v2.4
- **Supersedes:** ADR-0004 delegation assumption

#### Context

ADR-0004 assumed Cowork inherits Claude Code's `Agent` dispatch and could run the
`cc_coordinator` -> `cc_translator` delegation chain, pending a small-book
verification. Real-world Cowork testing disproved this: Cowork's `Agent` tool
exposes only **built-in** agents, so project-defined `cc_*` subagents are not
dispatchable. Testing also showed `uv run python main.py` fails in Cowork's Linux
sandbox because the committed `.venv` is a Windows virtualenv; the working form is
`UV_CACHE_DIR=/tmp/uv-cache uv run --isolated --python 3.13 main.py ...`.

#### Decision

Reuse the OpenCode dispatch shape for Cowork without adding a `cw-*` adapter tree:

- Add a **Cowork Fallback Dispatch** block to `.harness/source/dispatch/translate-cc.md`
  (and therefore to the generated `cc-translate-book` skill). Under Cowork the Main
  Agent runs the compact per-chapter loop itself (no Coordinator tier) and
  dispatches a built-in `general-purpose` agent per chapter, instructing it to read
  and follow `.claude/agents/cc_translator.md`; metadata uses
  `.claude/agents/cc_metadata_translator.md`.
- Document the isolated-venv CLI form and the no-custom-subagent reality in the
  Cowork capability panel (`cw.md`).

The guide-only Cowork profile from ADR-0004 is retained — no `cw-*` skills or
agents are generated. Only the cc dispatch text and the Cowork panel change.

#### Consequences

- Cowork can run the full translation loop using a built-in worker, with token
  protection intact: the Main Agent never reads raw chapters; only the dispatched
  general worker does.
- The Cowork path has no coordinator tier, matching OpenCode. Large-book batching
  is driven by the Main Agent loop in the skill body.
- Claude Code proper is unchanged: it still uses the `cc_coordinator` /
  `cc_translator` path; the fallback block is explicitly Cowork-scoped.
- The Cowork CLI form differs from Windows; the panel documents both.

#### Verification

- `.harness/source/dispatch/translate-cc.md` contains the `Cowork Fallback Dispatch`
  block with `general-purpose`, `cc_translator.md`, `uv run --isolated`, and
  `no separate subagent tier`.
- The generated `.claude/skills/cc-translate-book/SKILL.md` contains the fallback.
- The `cw` panel documents the isolated-venv CLI, the not-dispatchable reality, and
  the general-agent dispatch.
- `tools/sync_harness_adapters.py --check` reports a clean tree.
```

- [ ] **Step 5: Run the architecture test**

Run:
```bash
$env:UV_CACHE_DIR="$PWD/.uv-cache"; $env:PYTHONUTF8=1
uv run pytest tests/test_harness_source_contract.py::test_architecture_documents_cowork_support -q
```
Expected: PASS — `ADR-0004`, `ADR-0005`, `v2.4`, `guide_profiles`, `general-purpose` all present.

- [ ] **Step 6: Commit**

```bash
git add ARCHITECTURE.md
git commit -m "docs: add ADR-0005 Cowork general-agent dispatch (v2.4)"
```

---

### Task 7: Full verification

- [ ] **Step 1: Run the whole suite**

Run:
```bash
$env:UV_CACHE_DIR="$PWD/.uv-cache"; $env:PYTHONUTF8=1
uv run pytest -q
```
Expected: all pass (prior baseline 317 passed, 1 skipped) with the added tests green.

- [ ] **Step 2: Lint**

Run:
```bash
$env:UV_CACHE_DIR="$PWD/.uv-cache"; $env:PYTHONUTF8=1
uv run ruff check .
```
Expected: clean.

- [ ] **Step 3: Final sync check**

Run:
```bash
$env:UV_CACHE_DIR="$PWD/.uv-cache"; $env:PYTHONUTF8=1
uv run python tools/sync_harness_adapters.py --check
```
Expected: clean tree.

---

## Notes

- Commands are shown in PowerShell form per project convention. Under bash, set env inline (`UV_CACHE_DIR="$PWD/.uv-cache" PYTHONUTF8=1 uv run ...`).
- Do not hand-edit any generated file under `.claude/`, `.agent/`, `.opencode/`, `.codex/`, `AGENTS.md`, or `CLAUDE.md`; regenerate via the sync tool (Task 5).
- The Cowork fallback is documentation/instruction only — no Python logic in `sync_harness_adapters.py` changes, keeping the blast radius to source markdown + tests.
