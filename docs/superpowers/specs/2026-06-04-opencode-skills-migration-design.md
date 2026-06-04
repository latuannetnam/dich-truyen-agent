# OpenCode-Native Skills for the Novel Translation Pipeline

**Date:** 2026-06-04
**Status:** Design approved across 4 sections. Spec self-review complete.

## 1. Problem

The novel translation project has skill definitions for **Antigravity** (`.agent/skills/`) and **Claude Code** (`.claude/skills/`) runtimes, but the project is increasingly run in **OpenCode** (the user is currently in an OpenCode session). The existing mirrors assume runtime-specific tools (`Bash`, `Agent({subagent_type})`, `Workflow({...})`) that either do not exist or have different names in OpenCode, and the external-LLM guardrail is implemented as a Claude-format PreToolUse hook that OpenCode ignores.

## 2. Goals

1. Make the four pipeline skills (`crawl-book`, `translate-book`, `check-translation`, `export-book`) work natively in OpenCode **without** modifying the Antigravity or Claude Code originals.
2. Port the external-LLM guardrail to a **declarative** OpenCode form (`permission.bash` rules in `opencode.json`), accepting the trade-off that the Python file-content scan from the original Claude hook is dropped.
3. Add a parallel `oc-translator` subagent for OpenCode's `task` tool, mirroring `.claude/agents/translator.md`.
4. Keep both runtimes usable in the same repository. The `oc-` prefix namespacing makes the OpenCode variant explicit and easy to retire later if desired.

## 3. Non-Goals

- Modifying `.agent/skills/`, `.claude/skills/`, `.claude/agents/`, or `.claude/hooks/`.
- Replacing the Python file-content scan with a plugin (declarative permission rules only, by user decision).
- Touching `main.py`, `src/`, or any other runtime code.
- Building a `Workflow` equivalent in OpenCode; the sequential loop is embedded in the `oc-translate-book` skill body.
- Auto-migrating or auto-converting between formats; the mirror is a hand-written parallel.

## 4. File Layout

### New files (6)

| Path | Purpose |
|---|---|
| `.opencode/skill/oc-crawl-book/SKILL.md` | OpenCode-native crawl skill |
| `.opencode/skill/oc-translate-book/SKILL.md` | OpenCode-native translate skill (embedded loop) |
| `.opencode/skill/oc-check-translation/SKILL.md` | OpenCode-native QA skill |
| `.opencode/skill/oc-export-book/SKILL.md` | OpenCode-native export skill |
| `.opencode/agent/oc-translator.md` | OpenCode translator subagent |
| `docs/superpowers/specs/2026-06-04-opencode-skills-migration-design.md` | This spec |

### Modified files (2)

| Path | Change |
|---|---|
| `opencode.json` | Additive: `permission.bash` deny rules, optional `agent.oc-translator` registration |
| `AGENTS.md` | Additive append: a short "OpenCode-Native Skill Variants" section |

### Untouched

`.agent/skills/`, `.claude/skills/`, `.claude/agents/`, `.claude/hooks/`, `main.py`, `src/`. New test files added in `tests/`; existing tests untouched.

## 5. Skill Content Adaptations

Per-skill mapping of Claude Code → OpenCode:

| Concern | Claude Code | OpenCode |
|---|---|---|
| Tool names | `Bash`, `Read`, `Edit`, `Glob`, `Grep`, `Write`, `Agent({subagent_type})` | `bash`, `read`, `edit`, `glob`, `grep`, `write`, `task({subagent_type})` |
| Workflow orchestrator | `Workflow({name, args})` | None — loop embedded in skill body |
| External-LLM guardrail | `.claude/hooks/check_external_llm.py` (PreToolUse hook, scans .py files) | `permission.bash` rules in `opencode.json` (command-string only) |
| Subagent dispatch | `Agent({subagent_type: "translator", description, prompt})` | `task({subagent_type: "oc-translator", description, prompt})` |
| Subagent allowlist | Frontmatter `tools: Read, Write, Glob, Grep` | Frontmatter `tools: {read: true, write: true, glob: true, grep: true, bash: false, ...}` + `permission: {bash: deny, ...}` |
| PowerShell env var | `$env:PYTHONUTF8=1` | Identical |
| `read` with line limit | `Read(path, limit: 3)` | `read` tool with explicit `limit: 3` argument |

## 6. `oc-translator` Subagent

**Path:** `.opencode/agent/oc-translator.md`

### Frontmatter

```yaml
---
description: "Use when dispatching a single Chinese novel chapter to be translated into Vietnamese with strict Xianxia/Tu Chan (Tiên Hiệp / Tu Chân) style, glossary fidelity, and lexical sandbox enforcement. Dispatch one instance per chapter — never reuse for multiple chapters, and never use for QA, crawling, or export."
mode: subagent
model: inherit
hidden: true
tools:
  read: true
  write: true
  glob: true
  grep: true
  bash: false
  webfetch: false
  task: false
  edit: false
permission:
  bash: deny
  edit: deny
  webfetch: deny
  task: deny
  websearch: deny
---
```

### Body

Near-verbatim copy of `.claude/agents/translator.md`'s 10-step procedure, lexical sandbox table, and JSON return contract. Tool names in body text changed to lowercase OpenCode names. The "you have NO Bash" line is replaced by a reference to the frontmatter deny rules.

## 7. `opencode.json` Augmentation

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "plugin": ["superpowers@git+https://github.com/obra/superpowers.git"],

  "permission": {
    "bash": {
      "*": "allow",
      "rm -rf /*": "deny",
      "*api.openai.com*": "deny",
      "*openrouter.ai*": "deny",
      "*api.anthropic.com*": "deny",
      "*generativelanguage.googleapis.com*": "deny",
      "*api.deepseek.com*": "deny",
      "*OPENAI_API_KEY*": "deny",
      "*OPENROUTER_API_KEY*": "deny",
      "*ANTHROPIC_API_KEY*": "deny",
      "*GEMINI_API_KEY*": "deny",
      "*DEEPSEEK_API_KEY*": "deny",
      "*import openai*": "deny",
      "*import anthropic*": "deny",
      "*from openai*": "deny",
      "*from anthropic*": "deny"
    },
    "edit": "allow",
    "read": "allow",
    "glob": "allow",
    "grep": "allow",
    "webfetch": "ask",
    "websearch": "ask"
  }
}
```

### Ordering rationale

`*` is the broad base (first); narrow deny rules come last. OpenCode evaluates the LAST matching rule, so denials override the allow for matching commands. The new `rm -rf /*` safety net is added (not present in the original Claude setup) because it costs nothing.

### Dropped capability

Python file-content scanning (e.g., `python -c "import openai"` *without* `import openai` appearing in the command line) is not caught. Documented as a known trade-off in the `oc-translate-book` skill body and `AGENTS.md` cross-reference.

## 8. Sequential Translate Loop (embedded)

OpenCode has no `Workflow` tool. The `oc-translate-book` skill body describes a **manual one-chapter-per-invocation** loop mirroring the Claude mirror's "Steps 1–8" manual mode.

### Loop structure (preserved verbatim from the existing manual mode)

1. Verify gate (`check-gate`)
2. Query next chapter (`show-translation-progress`)
3. Prepare context (`prepare-translation-context`)
4. Resolve absolute paths — use `pathlib.Path(...).resolve()` for Windows-safe absolute paths (subagent runs in its own cwd)
5. `task()` dispatch to `oc-translator`
6. Lightweight staging verify (`read` with `limit: 3`)
7. Promote (`promote-chapter`)
8. Retry/halt/loop: 3 attempts max, `Start-Sleep -Seconds 5` (PowerShell) backoff between attempts, halt on exhaustion, workspace stays clean at last promoted chapter

### Long-run behavior

After a successful `promote-chapter`, the agent uses its own judgment to return to Step 2 to continue with the next chapter, or stop if the user invoked the skill for a single chapter. There is **no automatic long-run orchestrator** in OpenCode (no `Workflow` equivalent). For 10+ chapters, the user is expected to invoke the skill (or have the agent decide) repeatedly; this is a documented ergonomic gap.

## 9. `AGENTS.md` Cross-Reference (append-only)

```markdown
## OpenCode-Native Skill Variants

For users running the **OpenCode** runtime (vs. Claude Code or Antigravity), parallel `oc-*` skills live in `.opencode/skill/`:

- `oc-crawl-book` — equivalent of `crawl-book`, uses the `bash` tool
- `oc-translate-book` — equivalent of `translate-book`, uses `task({subagent_type:"oc-translator"})` and embeds the sequential loop in the skill body (no `Workflow` tool)
- `oc-check-translation` — equivalent of `check-translation`
- `oc-export-book` — equivalent of `export-book`
- `oc-translator` (subagent) — equivalent of `.claude/agents/translator.md`

The `.agent/skills/*` and `.claude/skills/*` versions are NOT modified. Both runtimes continue to work. See `opencode.json` `permission.bash` for the OpenCode-specific external-LLM guardrail (declarative, command-string only — Python file-content scan from the original hook is dropped).
```

## 10. Test Strategy

Four small test files in `tests/`:

1. **`tests/test_oc_skills_discoverable.py`** — glob `.opencode/skill/*/SKILL.md`, parse YAML frontmatter, assert `name` matches folder, `description` non-empty, contains "Use when" pattern.
2. **`tests/test_opencode_json_valid.py`** — load `opencode.json`, assert `$schema` present, assert `permission.bash` denies contain all 5 endpoints + 5 env vars + 4 import patterns + `rm -rf /*` safety.
3. **`tests/test_oc_translator_frontmatter.py`** — parse `.opencode/agent/oc-translator.md`, assert `mode: subagent`, `hidden: true`, `tools.bash == false`, `permission.bash == "deny"`.
4. **`tests/test_ag_md_references.py`** — grep `AGENTS.md` for the 5 `oc-*` names.

Run with:

```powershell
uv run pytest tests/test_oc_skills_discoverable.py tests/test_opencode_json_valid.py tests/test_oc_translator_frontmatter.py tests/test_ag_md_references.py -q
```

## 11. Data Flow (translate-book, most complex)

```
Main agent (build mode) -> reads `oc-translate-book` skill
  -> bash: check-gate
  -> bash: show-translation-progress -> parse reason JSON
  -> bash: prepare-translation-context -> parse reason JSON
  -> compute absolute paths (staged_txt, staged_yaml) via pathlib.Path(...).resolve()
  -> task({subagent_type: "oc-translator", description, prompt})
       - oc-translator runs in isolated context window
       - reads raw_path, style_path, glossary_path, prev_translation_path (Read-only, file-scoped)
       - writes staged_txt (and optionally staged_yaml) to absolute paths
       - returns ONLY the success/error JSON block
  -> read(staged_txt, limit: 3) -> verify title line
  -> bash: promote-chapter
  -> retry up to 3 times with 5s backoff; halt on exhaustion
```

## 12. Error Handling

- Translator subagent error → retry with `Start-Sleep -Seconds 5` backoff
- Promote failure → retry with backoff
- 3 failed attempts → halt, leave workspace clean at last promoted chapter
- `blocked` state from `show-translation-progress` → halt and report gap
- Permission denial from `permission.bash` → user sees denial reason in tool output; agent must reformulate the command without the banned string

## 13. Acceptance Criteria

1. All 4 `oc-*` skill `SKILL.md` files exist at the paths listed in Section 4.
2. `oc-translator.md` exists with the frontmatter in Section 6.
3. `opencode.json` validates against the published schema and contains all 16 deny rules (1 base `*` allow + 1 `rm -rf /*` deny + 5 endpoints + 5 env vars + 4 import patterns).
4. `AGENTS.md` has the cross-reference section appended.
5. All 4 test files pass: `uv run pytest tests/test_oc_*.py tests/test_opencode_json_valid.py tests/test_ag_md_references.py -q`
6. Manual: **quit and restart the OpenCode CLI session** (config is loaded once at start, not hot-reloaded) → trigger phrase "translate the next chapter of books/xianfu-changsheng" → `oc-translate-book` skill is invoked → `task()` dispatches to `oc-translator` → translation completes → `promote-chapter` succeeds.
7. Manual: After restart → execute `python -c "import openai"` via the `bash` tool → command is denied with reason visible to the user.

## 14. Out-of-Scope Trade-offs (Documented)

- **No `Workflow` equivalent.** OpenCode has no orchestrator tool. The translate loop is embedded in the skill body. For long runs, the agent (or user) loops manually per Section 8.
- **No Python file-content scan.** The original hook read `.py` files referenced in commands and scanned for `import openai` etc. OpenCode's `permission.bash` only matches the command string. In practice, the translator subagent never writes Python that imports banned libraries, and the dispatch path is via the `task` tool (not bash), so this gap is acceptable per the user's Q3 decision.
- **Duplicate skill loading.** OpenCode auto-loads `~/.claude/skills/*` and may auto-load project-local `.claude/skills/*`. The `oc-` prefix is the only namespacing mitigation. Future work (out of scope here) could add `OPENCODE_DISABLE_CLAUDE_CODE_SKILLS=1` to the user's shell init, or rename the Claude mirrors to `cc-*` for symmetry.
- **No `rm -rf /*` safety in the original Claude setup.** New safety net added in Section 7 because `permission.bash` supports it for free; this is a strict improvement, not a regression.

## 15. Spec Self-Review Trail

- Placeholder scan: clean.
- Internal consistency: 16 deny rules counted in Section 7 match the assertions in Section 10 and Section 13.
- Scope: single PR, manageable.
- Ambiguity fixes applied: clarified OpenCode restart semantics, PowerShell backoff, Windows path resolution, and long-run loop behavior.
