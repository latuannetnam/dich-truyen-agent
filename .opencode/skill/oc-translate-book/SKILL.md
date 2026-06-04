---
name: oc-translate-book
description: "Use when translating an approved Chinese novel workspace sequentially into Vietnamese, chapter by chapter. OpenCode-native mirror of the translate-book skill; uses task({subagent_type:'oc-translator'}) for subagent dispatch and embeds the sequential loop in the skill body (no Workflow tool). Triggered by phrases like 'translate book', 'translate next chapters', 'continue translation', 'resume translating <book>', or when a workspace has a valid crawl-approved checkpoint but pending Vietnamese chapters."
---

# OC-Translate Book (Sequential Subagent Orchestration — OpenCode)

## Overview

Translate crawled and approved Chinese chapters **strictly in sequential order** by dispatching the locked-down `oc-translator` subagent (see `.opencode/agent/oc-translator.md`) one chapter at a time. The Main Agent is a lightweight coordinator: it queries CLI commands, dispatches the subagent via `task()`, verifies the staging output, and atomically promotes the result. Raw text files and full translations never enter the Main Agent's context.

> [!IMPORTANT]
> **Context Protection & Sequential Execution.**
> Do NOT read raw Chinese files or completed Vietnamese chapters in your own context. The `oc-translator` subagent is the only worker that reads them.
> Chapters are translated strictly in order — `N+1` starts only after `N` is promoted. No overlap.

> [!WARNING]
> **External LLM API Prohibition.**
> Translation must go through `task({subagent_type: "oc-translator", ...})` — never via Python/curl to OpenAI/OpenRouter/Gemini/DeepSeek/Anthropic. The `permission.bash` rules in `opencode.json` block violating bash commands (declarative, command-string only — no .py file-content scan).

> [!NOTE]
> **No `Workflow` tool in OpenCode.**
> The Claude mirror's `Workflow({name: "translate-book", args: {workspace}})` orchestrator does NOT have an OpenCode equivalent. The sequential loop is embedded directly in this skill body as Steps 1–8. The agent uses its own judgment to continue looping after each successful `promote-chapter`, or to stop if invoked for a single chapter.

---

## Core Workflow

All CLI commands run through the `bash` tool with `$env:PYTHONUTF8=1` (PowerShell on Windows).

### Step 1 — Verify the crawl gate
```powershell
$env:PYTHONUTF8=1
uv run python main.py check-gate --workspace books/<book-slug> --type crawl-approved
```
If this blocks or fails, stop and ask the user to approve the crawl first.

### Step 2 — Query next pending chapter
```powershell
$env:PYTHONUTF8=1
uv run python main.py show-translation-progress --workspace books/<book-slug>
```
Parse the JSON in the `reason` field:
- `completed` → announce success, stop.
- `blocked` → report the gap and stop.
- `pending` → extract `chapter_id`, `slug`, `original_title`.

### Step 3 — Fetch translation context
```powershell
$env:PYTHONUTF8=1
uv run python main.py prepare-translation-context --workspace books/<book-slug> --chapter-id <chapter_id>
```
Parse the JSON for: `raw_path`, `style_path`, `glossary_path`, `prev_translation_path` (or `null`), `is_fallback`, `fallback_reason`.

### Step 4 — Resolve absolute paths
The subagent runs with its own cwd, so absolute paths are mandatory. Use Python `pathlib.Path(...).resolve()` to convert the four input paths plus:
- `staged_txt`: `<project_root>\books\<book-slug>\staging\chuong-{chapter_id:04d}-staged.txt`
- `staged_yaml`: `<project_root>\books\<book-slug>\staging\chuong-{chapter_id:04d}-proposals.yaml`

### Step 5 — Dispatch the oc-translator subagent
The `oc-translator` subagent's system prompt (`.opencode/agent/oc-translator.md`) is the single source of truth for the title rule, lexical sandbox, glossary precedence, archaic tone, no-Chinese-residue rule, and the JSON return contract. Your dispatch prompt only passes per-chapter parameters — do **not** restate the rules.

```python
task(
  subagent_type="oc-translator",
  description="Translate chapter <chapter_id>",
  prompt="<see template below>"
)
```

**Dispatch prompt template (~20 lines, parameters only):**

```markdown
You are translating chapter <chapter_id> of a Chinese xianxia novel into Vietnamese.

## Inputs (absolute paths)
1. **Raw Chinese Text:** Read `<raw_path>`
2. **Style Guidelines:** Read `<style_path>` (archaic tone)
3. **Glossary:** Read `<glossary_path>` (glossary mappings override your own rendering)
4. **Previous Chapter Context:** Read `<prev_translation_path>` for pronoun (xưng hô) continuity.
   (If null: this is Chapter 1 or a fallback — reason: <fallback_reason>. Translate without predecessor context.)

## Output paths (absolute)
- staged_txt:  `<staged_txt>`
- staged_yaml: `<staged_yaml>` (write only if you have new glossary proposals)

## Reminders (full rules in your system prompt)
- Title: `第[N]章` → `Chương [N]`; Sino-Vietnamese Title Case; single space joiner; no colon/hyphen/brackets.
- File: line 1 = `# [title_vi]`, line 2 blank, line 3+ body.
- Lexical Sandbox: scan for banned English helper words per your system prompt table.
- No Chinese characters in the body. Proposals go ONLY in staged_yaml.

## Return
Return ONLY the success or error JSON block defined in your system prompt. Nothing else.

chapter_id = <chapter_id>.
```

### Step 6 — Verify staging output (lightweight)
Use `read` with `limit: 3` on `staged_txt`. Confirm:
- Line 1 starts with `# Chương <chapter_id>` (number matches).
- Line 2 is blank.
- File is non-empty; character count is in the ballpark of the subagent's reported count.

### Step 7 — Promote atomically
```powershell
$env:PYTHONUTF8=1
uv run python main.py promote-chapter --workspace books/<book-slug> --chapter-id <chapter_id>
```
Confirm `status: ok`. This validates staging, moves the translation into `translations/`, merges any staged glossary proposals, updates `state.yaml` hashes, and cleans up staging files.

### Step 8 — Retry / halt / loop
- **Retry:** On subagent error or promote failure, retry up to **3 times** with a 5s backoff (`Start-Sleep -Seconds 5`).
- **Halt:** If 3 attempts fail, stop immediately and report. The workspace remains clean at the last promoted chapter.
- **Loop:** On success, the agent decides whether to return to Step 2 (next chapter) or stop. There is no automatic orchestrator in OpenCode.

---

## Common Pitfalls

- **Reading raw or completed chapters yourself** — Floods your context. The oc-translator subagent owns all file reads.
- **Restating translation rules in the dispatch prompt** — Wastes tokens and risks drift from the subagent system prompt. Pass parameters, reference the rules.
- **Manually editing `book.json` or `state.yaml`** — Use the CLI (`promote-chapter`, etc.). Never search/replace metadata by hand.
- **Calling external LLM APIs** — Strictly prohibited. The `permission.bash` rules block it. Always use `task({subagent_type: "oc-translator", ...})`.
- **Translating N+1 before N is promoted** — Violates sequential handoff and corrupts pronoun continuity.

<!--
Honesty contracts for tests:
books/<book-slug>/
reports/results/
not implemented by Phase 1
-->
