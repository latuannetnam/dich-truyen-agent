---
name: oc-translate-book
description: "Use when translating an approved Chinese novel workspace sequentially into Vietnamese, chapter by chapter. OpenCode-native mirror of the translate-book skill; uses task({subagent_type:\"general\"}) with the oc-translator system prompt inlined, and embeds the sequential loop in the skill body (no Workflow tool). Triggered by phrases like 'translate book', 'translate next chapters', 'continue translation', 'resume translating <book>', or when a workspace has a valid crawl-approved checkpoint but pending Vietnamese chapters."
---

# OC-Translate Book (Sequential Subagent Orchestration — OpenCode)

## Overview

Translate crawled and approved Chinese chapters **strictly in sequential order** by dispatching the built-in `general` subagent with the translator system prompt inlined (see `.opencode/agent/oc-translator.md` for the canonical prompt body). The Main Agent is a lightweight coordinator: it queries CLI commands, dispatches the subagent via `task()`, verifies the staging output, and atomically promotes the result. Raw text files and full translations never enter the Main Agent's context.

> [!IMPORTANT]
> **Why `general`, not a custom subagent?**
> OpenCode Issue #17890 — `model: inherit` in custom (non-native) subagent frontmatter is parsed as `{ providerID: "inherit", modelID: "" }`, producing `ProviderModelNotFoundError`. Only built-in **native** subagents (`general`, `explore`) correctly inherit the parent model. The workaround: dispatch via `general` and inline the oc-translator system prompt in the dispatch body.

> [!IMPORTANT]
> **Context Protection & Sequential Execution.**
> Do NOT read raw Chinese files or completed Vietnamese chapters in your own context. The dispatched subagent is the only worker that reads them.
> Chapters are translated strictly in order — `N+1` starts only after `N` is promoted. No overlap.

> [!WARNING]
> **External LLM API Prohibition.**
> Translation must go through `task({subagent_type: "general", ...})` with the inlined translator prompt — never via Python/curl to OpenAI/OpenRouter/Gemini/DeepSeek/Anthropic. The `permission.bash` rules in `opencode.json` block violating bash commands (declarative, command-string only — no .py file-content scan).

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

### Step 1.5 — Verify and Translate Book Metadata
Check if the book's metadata (`book.yaml`) has been translated.
1. Read the contents of `books/<book-slug>/book.yaml` using your file reading tools.
2. Check if `translated_title` and `translated_author` are populated.
3. If they are missing or empty:
   - Dispatch the built-in `general` subagent via `task()` to translate the book title and author:
     ```python
     task(
       subagent_type="general",
       description="Translate book title '<title>' and author '<author>'",
       prompt="\"\"\"You are a highly specialized Chinese-to-Vietnamese novel translator. Translate the Chinese book title '<title>' and Chinese author name '<author>' into elegant Vietnamese Xianxia style.
       
       Return ONLY this JSON block:
       {
         \"translated_title\": \"<translated_title>\",
         \"translated_author\": \"<translated_author>\"
       }
       If an error occurs, return:
       {
         \"translated_title\": null,
         \"translated_author\": null,
         \"error_message\": \"<error details>\"
       }\"\"\"
     )
     ```
   - Extract `translated_title` and `translated_author` from the subagent's response.
   - Persist the translated metadata by running:
     ```powershell
     $env:PYTHONUTF8=1
     uv run python main.py update-book-metadata --workspace books/<book-slug> --translated-title "<translated_title>" --translated-author "<translated_author>"
     ```

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

### Step 5 — Dispatch via `general` with the translator prompt inlined
The translator system prompt (`.opencode/agent/oc-translator.md`, body section) is the single source of truth for the title rule, lexical sandbox, glossary precedence, archaic tone, no-Chinese-residue rule, and the JSON return contract. The orchestrator (you) reads the file, inlines the body verbatim into the dispatch prompt, then appends the per-chapter parameters.

**Procedure:**
1. Read `.opencode/agent/oc-translator.md` (use the `read` tool).
2. Copy the body (everything after the closing `---` frontmatter on line 21) verbatim into the dispatch prompt.
3. Append the per-chapter parameter block shown below.

```python
task(
  subagent_type="general",
  description="Translate chapter <chapter_id>",
  prompt="""<paste the body of .opencode/agent/oc-translator.md here, verbatim>

## Per-chapter dispatch parameters (appended by orchestrator)
- chapter_id = <chapter_id>
- raw_path = <raw_path>
- style_path = <style_path>
- glossary_path = <glossary_path>
- prev_translation_path = <prev_translation_path>  # null if Chapter 1 or fallback
- fallback_reason = <fallback_reason>  # "N/A" if not a fallback
- staged_txt = <staged_txt>
- staged_yaml = <staged_yaml>

## Tool allowlist (enforced via prompt — `general` is built-in and has all tools)
You have access to: `read`, `write`, `glob`, `grep`.
Do NOT use: `bash`, `webfetch`, `task`, `edit`, `todowrite`, `skill`, `websearch`.
If a task seems to require a blocked tool, fail with the error JSON block.

## Return
Return ONLY the success or error JSON block defined above. Nothing else."""
)
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

- **Reading raw or completed chapters yourself** — Floods your context. The dispatched subagent owns all file reads.
- **Restating translation rules in the dispatch prompt** — Wastes tokens and risks drift from the source prompt. Inline `.opencode/agent/oc-translator.md` verbatim; append only the per-chapter parameters.
- **Forgetting the tool allowlist override** — `general` is built-in and has all tools. The dispatch prompt MUST explicitly forbid `bash`, `webfetch`, `task`, `edit`, `todowrite`, `skill`, `websearch` or the subagent will misuse them.
- **Manually editing `book.json` or `state.yaml`** — Use the CLI (`promote-chapter`, etc.). Never search/replace metadata by hand.
- **Calling external LLM APIs** — Strictly prohibited. The `permission.bash` rules block it. Always use `task({subagent_type: "general", ...})` with the inlined prompt.
- **Translating N+1 before N is promoted** — Violates sequential handoff and corrupts pronoun continuity.

<!--
Honesty contracts for tests:
books/<book-slug>/
reports/results/
not implemented by Phase 1
-->
