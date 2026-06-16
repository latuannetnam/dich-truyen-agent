# Claude Cowork Harness Support — Design

- **Date:** 2026-06-16
- **Status:** Proposed
- **Architecture version target:** v2.3

## Problem

The translation pipeline supports four harnesses through generated, prefixed
adapters: Antigravity (`ag-*`), Claude Code (`cc-*`), OpenCode (`oc-*`), and
Codex (`codex-*`). We want the pipeline to run under **Claude Cowork**,
Anthropic's autonomous desktop agent (GA April 2026).

## Key facts about Cowork

Established through documentation research (sources noted in the discussion, not
reproduced here):

1. **Cowork is built on Claude Code** and shares its **plugin** model (skills +
   agents bundled). It reads the same `.claude/` filesystem conventions.
2. **Bash/CLI execution is supported**, so `uv run python main.py ...` works.
3. **Custom subagents** (`.claude/agents/*.md`) are supported through the plugin
   model. Whether a *skill body* can dispatch a subagent in Cowork is officially
   **undocumented**, but Cowork inherits Claude Code's `Agent` dispatch.
4. **Hooks are NOT fired** in Cowork — no PreToolUse/PostToolUse/settings.json
   hooks (known limitation, open feature request). This directly affects the
   project's `check_external_llm.py` guardrail hook.
5. Native `.claude/skills/` auto-discovery vs plugin-only loading is
   **undocumented**, but the plugin path is confirmed to load skills.

## Consequence that shapes the design

Because Cowork reads the same `.claude/` adapters as Claude Code, the existing
`cc-*` skills and `cc_*` agents **already load in Cowork**. The two real gaps are:

- The external-LLM guardrail **hook will not fire**, degrading enforcement to
  instruction level.
- Skill-body subagent **dispatch is undocumented** and must be verified before
  trusting large books.

A separate `cw-*` adapter tree was rejected: Cowork reads `.claude/`, not a
hypothetical `.cowork/` directory, so a `.cowork/` tree would be ignored, and
placing `cw-*` files into `.claude/` would cause **duplicate skill discovery**
with `cc-*` in both Claude Code and Cowork — a problem Cowork cannot suppress
(no hooks/config equivalent to `opencode.json`).

## Decision

Support Cowork as a **Claude-Code-compatible profile** that reuses the `cc-*`
adapters. Add documentation and harden the guardrail to be hook-independent.

**Net new generated adapter files: zero skills, zero agents.**

## Changes

### 1. Guardrail hardening (the one real edit)

The external-LLM guardrail is already embedded in skill/agent text in three of
four places:

- `.harness/source/skills/translate-book.md` — "Strict External API Prohibition"
  warning and the "Using External LLM APIs" pitfall. ✓
- `.harness/source/agents/translator.md` — operating rule 3. ✓
- `.harness/source/agents/metadata-translator.md` — explicit line. ✓
- `.harness/source/agents/coordinator.md` — **missing** an explicit external-LLM
  prohibition. ✗

**Edit:** Add an explicit operating rule to `coordinator.md` stating that no
external LLM API, endpoint, SDK import, API key, or external script may be used;
translation happens only through the harness-native translator subagent. This
ensures the prohibition holds at instruction level through the whole delegation
chain when Cowork does not fire the hook.

The `check_external_llm.py` hook is **unchanged** and remains active for Claude
Code, where hooks still fire. It is simply inert under Cowork.

### 2. Cowork capability panel

New source file `.harness/source/guides/panels/cw.md` documenting how the
pipeline runs in Cowork:

- Cowork is built on Claude Code; it loads the **`cc-*` skills directly**
  (e.g. invoke `cc-translate-book`, `cc-crawl-book`, `cc-check-translation`,
  `cc-export-book`).
- Use Bash for CLI commands (`uv run python main.py ...`).
- Use `Read` for bounded file inspection.
- Coordinator/translator delegation uses the same `cc_coordinator` and
  `cc_translator` `Agent` dispatch as Claude Code.
- **Hooks do not fire in Cowork**, so the external-LLM guardrail is enforced at
  instruction level (embedded in the skills and agents), not by
  `check_external_llm.py`.
- **Verify subagent dispatch works in Cowork before running large books**, since
  skill-body dispatch is officially undocumented and the token-protection model
  depends on the translator subagent being the only worker that reads raw files.

### 3. Tooling change to render a guide-only profile

`render_guides()` currently builds `AGENTS.md` and `CLAUDE.md` from
`manifest["harnesses"]` panels. Add a panel source that gets a guide entry but
**no** generated adapter set.

- `manifest.json`: add `"guide_profiles": ["cw"]`.
- `sync_harness_adapters.py` → `render_guides()`: after appending the four
  harness panels, append each `guide_profiles` panel to **both** the `AGENTS.md`
  "Harness Capability Matrix" and `CLAUDE.md` (Cowork reads `CLAUDE.md`, so the
  panel must be present there). The matrix heading stays the same.
- `render_all()` is unchanged — it iterates only `manifest["harnesses"]` for
  skill/agent generation, so **no `cw-*` files are produced**.
- `skill_title`, `render_skill`, `render_agent`, and the `opencode.json` skill
  denial loops are all **unchanged** (they key off `harnesses`/known prefixes,
  and there are no `cw` skills to deny).
- `manifest.get("guide_profiles", [])` is read defensively so older manifests
  without the key still render.

### 4. Documentation

- `ARCHITECTURE.md`: add **ADR-0004** (Cowork as CC-compatible profile; the
  hooks gap; guardrail embedding; rejection of the full `cw-*` set for
  duplicate-discovery). Add a short Cowork note to the "Harness Adapter
  Architecture" section explaining that Cowork reuses the `cc-*` adapters and
  that `guide_profiles` render a panel without an adapter tree.
- Bump the architecture version banner to **v2.3** and add the v2.3 line to the
  "Current versions" list, since generated guide behavior changes.

### 5. Tests

Add to the existing harness-adapter test suite:

- **Cowork panel in guides:** assert `AGENTS.md` and `CLAUDE.md` each contain the
  Cowork panel markers — e.g. `Cowork`, `built on Claude Code`,
  `hooks do not fire`, and `cc-translate-book`.
- **Guardrail in coordinator:** assert the rendered `cc_coordinator` agent body
  (and the `coordinator.md` source) contains the external-LLM prohibition
  wording (e.g. `external LLM`).
- **No `cw-*` adapters generated:** assert no `cw-*` skill or `cw_*` agent files
  exist / are produced by `render_all()`.
- **Sync check:** `sync_harness_adapters.py --check` returns 0 after regeneration.
- Full `pytest -q` and `ruff check` remain green.

## Verification commands

```powershell
$env:PYTHONUTF8=1
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run python tools/sync_harness_adapters.py
uv run python tools/sync_harness_adapters.py --check
uv run pytest -q
uv run ruff check tools tests src main.py
```

## Out of scope

- `.harness/source/skills/translate-book.md` references a "Lexical Sandbox
  mapping table" (pitfall bullet) that ADR-0003 removed. This is a pre-existing
  inconsistency unrelated to Cowork and is tracked separately.
- No runtime Cowork-detection logic is added; the guardrail is hardened at
  instruction level for all harnesses rather than branching on runtime.

## Risks

- **Subagent dispatch in Cowork is undocumented.** If Cowork cannot dispatch a
  subagent from a skill body, the token-protection model cannot run large books
  there. Mitigation: the panel instructs users to verify dispatch on a small
  book first; this design does not claim large-book support in Cowork until
  verified. No code path assumes Cowork-specific dispatch behavior.
- **Cowork plugin/skill discovery specifics may evolve.** The design relies only
  on the documented fact that Cowork reads `.claude/` plugin adapters; it adds no
  Cowork-private file conventions that could drift.
