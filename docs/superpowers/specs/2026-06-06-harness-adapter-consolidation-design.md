# Multi-Harness Skill and Agent Consolidation Design

**Date:** 2026-06-06
**Status:** Design approved in-session. Spec self-review complete.

## 1. Problem

The repository currently carries parallel runtime surfaces for Antigravity (`.agent/`), Claude Code (`.claude/`), and OpenCode (`.opencode/`). These files mostly describe the same novel translation pipeline, but they diverge in frontmatter, tool names, subagent dispatch syntax, guardrails, and runtime discovery rules. The duplication has already produced drift, especially in translator prompt details.

The same problem also exists at the main-agent guide layer. `AGENTS.md` and `CLAUDE.md` describe the same workspace lifecycle, gates, translation ordering, context protection, and failure handling, but they are maintained as separate narrative documents with harness-specific examples embedded throughout.

The desired end state is one canonical source of truth with committed harness-native adapters for Antigravity, Claude Code, OpenCode, and Codex. The adapters must be easy for each harness to discover and hard to confuse with another harness's files.

## 2. Decisions

1. Use a generator approach: canonical source files render committed harness adapters.
2. Commit the generated adapters in the repository.
3. Prefix every runtime-visible adapter name by harness:
   - Antigravity: `ag-*`
   - Claude Code: `cc-*`
   - OpenCode: `oc-*`
   - Codex: `codex-*`
4. Remove old unprefixed runtime-visible pipeline skills instead of keeping compatibility shims.
5. Optimize by behavioral variance: share deterministic CLI skills broadly, and specialize only the translation subagent dispatch path.
6. Consolidate root main-agent guides through the same generator model: shared orchestration logic with harness-specific capability panels.

## 3. Goals

- Maintain one canonical source for shared pipeline instructions and agent prompt bodies.
- Preserve harness-native discovery and invocation behavior through committed generated adapters.
- Avoid duplicate or confusing runtime-visible skills and agents.
- Keep translation context protection intact: the main agent must never read raw Chinese or full Vietnamese chapter files.
- Keep external LLM API prohibition intact across all harnesses.
- Add tests that catch generated adapter drift and cross-harness discovery mistakes.
- Keep `AGENTS.md`, `CLAUDE.md`, and any future harness guide files aligned by generating them from shared main-agent guide source.

## 4. Non-Goals

- Building a centralized app or service for translation orchestration.
- Making every harness use identical runtime files.
- Preserving the old unprefixed skill names as public entry points.
- Forcing all harnesses to use a coordinator subagent if the harness does not support nested orchestration safely.
- Replacing deterministic Python CLI helpers such as `crawl-book`, `check-translation`, or `export-book`.
- Removing harness-specific feature documentation. The goal is to isolate it, not flatten it away.

## 5. Architecture

Introduce a neutral canonical source tree, for example `.harness/source/`, that owns the reusable content:

- Shared pipeline skill bodies: crawl, translate, check translation, export.
- Shared agent bodies: translator and metadata translator.
- Optional shared coordinator body for harnesses that support useful nested orchestration.
- Shared main-agent guide body: workspace lifecycle, gates, phase responsibilities, context protection, sequential handoff, failure handling, and environment rules.
- Shared guardrail policy: banned external LLM endpoints, environment variables, SDK imports, and rationale.
- Harness render templates for frontmatter, folder layout, naming, tool vocabulary, and dispatch snippets.

A deterministic generator renders the committed adapters into harness folders:

- `.agent/skills/ag-*` and `.agent/agents/ag_*`
- `.claude/skills/cc-*` and `.claude/agents/cc_*`
- `.opencode/skill/oc-*` and `.opencode/agent/oc-*`
- `.codex/skills/codex-*` and `.codex/agents/codex_*` or the closest supported Codex-local convention
- Root guide files such as `AGENTS.md` and `CLAUDE.md`, plus any future harness-specific guide entrypoint required by OpenCode or Codex

Generated files include a header stating that they are generated from the canonical source and must not be edited directly.

## 6. Main-Agent Guide Consolidation

The root orchestration guides should follow the same shared-source model as skills and agents. The canonical source should separate common main-agent logic from harness capability details.

### 6.1 Shared Main-Agent Logic

This content is identical across harnesses:

- Workspace lifecycle and checkpoint gates.
- Phase responsibilities: init, crawl, approve crawl, translate, check translation, approve QA, export.
- CLI gate commands and UTF-8 environment rules.
- Token and context protection: the main agent never reads raw Chinese or full Vietnamese chapters.
- Sequential translation order and previous-chapter context handoff.
- Failure handling, retry limits, halt-on-failure, and resumability requirements.
- Policy that translation must use native harness delegation, not external LLM APIs.

### 6.2 Harness Capability Panels

Only the capability panel varies by harness. Each generated guide should include the same shared logic plus a concise panel for the active harness:

- Antigravity: prefixed `ag-*` skills, `run_command`, `view_file`, `invoke_subagent`, `ag_coordinator`, and Antigravity hook behavior.
- Claude Code: prefixed `cc-*` skills, `Bash`, `Read`, `Agent`, optional `Workflow`, and Claude Code hook behavior.
- OpenCode: prefixed `oc-*` skills, `bash`, `read`, `task`, `general` workaround when needed, and `opencode.json` permission behavior.
- Codex: prefixed `codex-*` skills, native subagent delegation through `spawn_agent` where available, Codex shell/tool constraints, and Codex guardrail documentation.

### 6.3 Rendered Guide Files

`AGENTS.md` should become the cross-harness root guide generated from shared main-agent logic and a compact capability matrix. It should point users to the active harness's prefixed entry points and explain that runtime adapters are generated.

`CLAUDE.md` should no longer be a manually maintained mirror. It should be generated from the same shared main-agent logic plus the Claude Code capability panel. Its examples should use `cc-*` names and Claude Code-native features.

If OpenCode or Codex requires a dedicated root guide filename later, that file should also be generated from the same source rather than written by hand.

## 7. Behavioral Tiers

### 7.1 Fully Shared CLI Skills

`crawl-book`, `check-translation`, and `export-book` are deterministic CLI workflows. They should render from the same canonical body for all harnesses, with only harness-specific wrappers:

- Frontmatter syntax.
- Prefixed skill names.
- Tool wording such as `Bash` vs `bash`.
- Runtime notes when a harness needs them.

The generated names are:

- `ag-crawl-book`, `cc-crawl-book`, `oc-crawl-book`, `codex-crawl-book`
- `ag-check-translation`, `cc-check-translation`, `oc-check-translation`, `codex-check-translation`
- `ag-export-book`, `cc-export-book`, `oc-export-book`, `codex-export-book`

### 7.2 Partially Shared Translation Skill

`translate-book` is the only pipeline skill with substantial harness-specific behavior because it dispatches subagents. Its canonical source should be split into:

- Shared invariant workflow: crawl gate check, metadata translation check, sequential chapter order, translation context preparation, staging first-lines verification, atomic promotion, retries, and halt conditions.
- Harness-specific dispatch blocks:
  - Antigravity: `invoke_subagent` with `ag_coordinator`, `ag_translator`, and `ag_metadata_translator`.
  - Claude Code: `Agent({ subagent_type: "cc_translator" })`, with workflow support retained only if it remains useful and native.
  - OpenCode: `task({ subagent_type: "general" })` with the translator prompt body inlined if the custom subagent inheritance bug still applies.
  - Codex: native `spawn_agent`-style instructions where Codex supports subagent delegation. The adapter must state that translation requires native subagent delegation and must not be performed through shell/API calls.

The generated names are `ag-translate-book`, `cc-translate-book`, `oc-translate-book`, and `codex-translate-book`.

### 7.3 Shared Agent Bodies With Harness Wrappers

The translator and metadata translator prompts should be shared. Generated wrappers vary:

- Frontmatter shape.
- Agent name prefix.
- Tool allowlist representation.
- Tool vocabulary in body text.
- Dispatch compatibility notes.

The coordinator should be generated only for harnesses where nested orchestration is safe and useful. Antigravity clearly keeps an `ag_coordinator`. OpenCode should not get a coordinator while it relies on the `general` workaround. Claude Code and Codex coordinators should be added only if their native subagent model supports nested dispatch without confusing the runtime.

## 8. Data Flow

For normal use, the main agent reads the generated root guide for its harness, then discovers and calls committed prefixed adapters. Users call `ag-crawl-book`, `cc-translate-book`, `oc-check-translation`, or `codex-export-book` based on the active harness.

For maintenance, edits happen in the canonical source files. A developer runs the sync command, for example:

```powershell
uv run python tools/sync_harness_adapters.py
```

The generator overwrites generated adapters. A check mode compares the committed adapters against a fresh render:

```powershell
uv run python tools/sync_harness_adapters.py --check
```

Tests fail if the generated files are stale.

## 9. Guardrails

The consolidation preserves the current translation safety model:

- Main agent never reads raw Chinese or full Vietnamese chapter files.
- Chapters are translated strictly in order.
- Translation halts on gaps.
- Retries are capped at 3.
- External LLM API calls are prohibited.
- Generated adapters are treated as read-only outputs.

Guardrail enforcement uses one shared policy but harness-specific mechanisms:

- Antigravity: generated or adapted `.agents/hooks/check_external_llm.py`.
- Claude Code: generated or adapted `.claude/hooks/check_external_llm.py`.
- OpenCode: generated or adapted `opencode.json` permission rules.
- Codex: generated or adapted project instructions plus any supported Codex-local hook or config. If no hook mechanism is available, tests must at least assert that the Codex adapter explicitly routes translation through native subagents and forbids shell/API translation.

OpenCode permission rules should deny unprefixed legacy skills and non-OpenCode prefixes such as `ag-*`, `cc-*`, and `codex-*`.

## 10. Discovery Safety

Runtime-visible adapters must be unambiguous:

- `.agent` contains only `ag-*` skills and `ag_*` agents for this pipeline.
- `.claude` contains only `cc-*` skills and `cc_*` agents for this pipeline.
- `.opencode` contains only `oc-*` skills and `oc-*` agents for this pipeline.
- `.codex` contains only `codex-*` skills and `codex_*` agents for this pipeline.
- Old unprefixed runtime-visible pipeline skills are removed.
- Tests assert that generated adapters do not contain another harness's dispatch syntax except in explicitly allowed documentation snippets.

## 11. Testing Strategy

Add generator correctness tests:

- Running the generator in check mode produces no diff for committed adapters.
- Every generated file contains a generated-file header.
- No generated adapter has stale unprefixed names like `name: crawl-book`.
- Shared CLI-only skills render from the same canonical body across harnesses, except known wrapper substitutions.
- Translate adapters include the correct harness dispatch block and exclude the other dispatch blocks.

Add harness discovery safety tests:

- `.agent` exposes only `ag-*` pipeline adapters.
- `.claude` exposes only `cc-*` pipeline adapters.
- `.opencode` exposes only `oc-*` pipeline adapters.
- `.codex` exposes only `codex-*` pipeline adapters.
- `opencode.json` denies unprefixed, `ag-*`, `cc-*`, and `codex-*` skill names.
- Existing hook and permission tests are updated to read from or validate against the shared guardrail policy.
- `AGENTS.md` and `CLAUDE.md` are generated from shared main-agent guide source and contain the correct harness capability panels.

Primary verification commands:

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run pytest
uv run python tools/sync_harness_adapters.py --check
```

## 12. Migration Notes

The migration is intentionally breaking for runtime skill names. Existing calls such as `crawl-book` and `translate-book` become invalid once the old unprefixed adapters are removed. Users must call the prefixed adapter for their active harness.

Documentation should update examples in generated `AGENTS.md`, generated `CLAUDE.md`, `README.md`, and any relevant tests/spec references to the new prefixed names.

Existing OpenCode `oc-*` names are retained. Antigravity and Claude Code are renamed to `ag-*` and `cc-*`. Codex receives new `codex-*` adapters.

## 13. Acceptance Criteria

1. Canonical source files exist for shared skills, shared agent bodies, shared main-agent guide logic, translation dispatch variants, and guardrail policy.
2. A deterministic sync command renders all committed harness adapters.
3. Old unprefixed runtime-visible pipeline skill directories are removed.
4. Generated adapter names are prefixed by harness.
5. CLI-only skills share one canonical body across harnesses.
6. `translate-book` shares invariant workflow text but renders harness-specific subagent dispatch.
7. Translator and metadata translator bodies are shared across harness wrappers.
8. OpenCode permission rules prevent accidental invocation of non-OpenCode and legacy skill names.
9. Generator check mode and the full test suite pass.
10. `AGENTS.md` and `CLAUDE.md` are generated from the shared main-agent guide source.
11. `AGENTS.md` documents the generated adapter model and the prefixed entry points for all harnesses.
12. `CLAUDE.md` uses the same main-agent logic as `AGENTS.md`, with only Claude Code capability details and examples varying.

## 14. Spec Self-Review

- Placeholder scan: clean. No unresolved placeholder markers.
- Internal consistency: the architecture matches the approved generator approach, committed adapters, harness prefixes, all four harness targets, root guide consolidation, and removal of old unprefixed runtime files.
- Scope check: focused on main-agent guide, skill, and agent adapter consolidation, generation, discovery safety, and guardrails. Runtime translation CLI behavior remains out of scope.
- Ambiguity check: clarified that root guide logic and CLI-only skills are shared, while translation dispatch and harness capability panels vary by harness.
