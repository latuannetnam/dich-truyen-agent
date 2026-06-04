---
name: translate-book
description: Use when translating an approved Chinese novel workspace sequentially into Vietnamese, chapter by chapter. Triggered by phrases like "translate book", "translate next chapters", "continue translation", "resume translating <book>", or when a workspace has a valid crawl-approved checkpoint but pending Vietnamese chapters.
---

# Translate Book (Sequential Subagent Orchestration — Claude Code)

## Overview

Translate crawled and approved Chinese chapters **strictly in sequential order** by dispatching the locked-down `translator` subagent (see [.claude/agents/translator.md](../../agents/translator.md)) one chapter at a time. The Main Agent is a lightweight coordinator: it queries CLI commands, dispatches the subagent, verifies the staging output, and atomically promotes the result. Raw text files and full translations never enter the Main Agent's context.

> [!IMPORTANT]
> **Context Protection & Sequential Execution.**
> Do NOT read raw Chinese files or completed Vietnamese chapters in your own context. The `translator` subagent is the only worker that reads them.
> Chapters are translated strictly in order — `N+1` starts only after `N` is promoted. No overlap.

> [!WARNING]
> **External LLM API Prohibition.**
> Translation must go through `Agent({subagent_type: "translator", ...})` — never via Python/curl to OpenAI/OpenRouter/Gemini/DeepSeek/Anthropic. The PreToolUse hook at `.claude/hooks/check_external_llm.py` will block violating Bash commands.

> [!TIP]
> **Two execution modes:**
> - **Manual loop (this skill)** — Steps 1–8 below, one chapter at a time. Best for 1–5 chapters or troubleshooting.
> - **Workflow orchestration** — `Workflow({ name: "translate-book", args: { workspace: "books/<slug>" } })` runs the same loop deterministically with `runId` resumability. Best for 10+ unattended chapters. See [.claude/workflows/translate-book.js](../../workflows/translate-book.js).

---

## Core Workflow

All CLI commands run through the Bash tool with `$env:PYTHONUTF8=1` (PowerShell on Windows).

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
The subagent runs with its own cwd, so absolute paths are mandatory. Use PowerShell `Resolve-Path` or Python `pathlib.Path(...).resolve()` to convert the four input paths plus:
- `staged_txt`: `<project_root>\books\<book-slug>\staging\chuong-{chapter_id:04d}-staged.txt`
- `staged_yaml`: `<project_root>\books\<book-slug>\staging\chuong-{chapter_id:04d}-proposals.yaml`

### Step 5 — Dispatch the translator subagent
The `translator` subagent's system prompt (`.claude/agents/translator.md`) is the single source of truth for the title rule, lexical sandbox, glossary precedence, archaic tone, no-Chinese-residue rule, and the JSON return contract. Your dispatch prompt only passes per-chapter parameters — do **not** restate the rules.

```
Agent({
  description: "Translate chapter <chapter_id>",
  subagent_type: "translator",
  prompt: <see template below>
})
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
Use `Read(staged_txt, limit: 3)`. Confirm:
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
- **Retry:** On subagent error or promote failure, retry up to **3 times** with a 5s backoff.
- **Halt:** If 3 attempts fail, stop immediately and report. The workspace remains clean at the last promoted chapter.
- **Loop:** On success, go back to Step 2.

---

## Common Pitfalls

- **Reading raw or completed chapters yourself** — Floods your context. The translator subagent owns all file reads.
- **Restating translation rules in the dispatch prompt** — Wastes tokens and risks drift from the subagent system prompt. Pass parameters, reference the rules.
- **Manually editing `book.json` or `state.yaml`** — Use the CLI (`promote-chapter`, etc.). Never search/replace metadata by hand.
- **Calling external LLM APIs** — Strictly prohibited. The PreToolUse hook blocks it. Always use `Agent({subagent_type: "translator", ...})`.
- **Translating N+1 before N is promoted** — Violates sequential handoff and corrupts pronoun continuity.

<!--
Honesty contracts for tests:
books/<book-slug>/
reports/results/
not implemented by Phase 1
-->
