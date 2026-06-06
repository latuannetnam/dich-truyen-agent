---
name: "translate-book"
description: "Translate an approved novel workspace sequentially"
metadata:
  short-description: "Translate an approved novel workspace sequentially"
---

# Translate Book (Sequential Agent Orchestration Mode)

## Overview

Translate crawled and approved Chinese chapters sequentially using context-isolated translator subagents. The Main Agent acts as a lightweight coordinator, looping through pending chapters, querying translation contexts, dispatching specialized subagents to perform translation using the native `invoke_subagent` tool, and atomically promoting the outputs. This prevents raw text files or massive translations from flooding the Main Agent's context window, ensuring high token efficiency and consistent pronoun (xưng hô) continuity.

> [!IMPORTANT]
> **Context Protection & Sequential Execution:**
> Do **NOT** read raw source Chinese files or complete Vietnamese chapters into your own Main Agent session. Spawning subagents keeps your context window clear and allows translating hundreds of chapters continuously. 
> Chapters are translated **strictly in order** so that each chapter `N` can receive the completed Vietnamese translation of chapter `N-1` as narrative context.

> [!WARNING]
> **Strict External API Prohibition:**
> You are strictly forbidden from using external LLM APIs (e.g., OpenRouter, OpenAI, Gemini) via Python scripts, curl, or any other external tool to perform the translation. You MUST only use the native Antigravity `invoke_subagent` capability as specified in this document.

---

## Core Workflow

### Step 1: Verify the Crawl Gate Checkpoint
Enforce that the workspace has an active and valid `crawl-approved` checkpoint before proceeding:
```bash
$env:PYTHONUTF8=1
uv run python main.py check-gate --workspace books/<book-slug> --type crawl-approved
```
If this command blocks or fails, stop the workflow and guide the user to review and approve the crawled raw contents first.

### Step 1.5: Verify and Translate Book Metadata
The Main Agent checks if the book's metadata (`book.yaml`) has been translated.
1. Read the contents of `books/<book-slug>/book.yaml` using the `view_file` tool.
2. Check if `translated_title` and `translated_author` are populated.
3. If they are missing or empty:
   - Spawn a specialized metadata translation subagent using the native `invoke_subagent` tool:
     ```json
     invoke_subagent({
       "Subagents": [
         {
           "Prompt": "Translate the metadata for the book. Title: '<title>', Author: '<author>'",
           "Role": "Chinese-to-Vietnamese Xianxia/Tu Chan Translator",
           "TypeName": "ag_metadata_translator"
         }
       ]
     })
     ```
   - Extract `translated_title` and `translated_author` from the subagent's JSON response.
   - Persist the translated metadata to the workspace by running:
     ```bash
     $env:PYTHONUTF8=1
     uv run python main.py update-book-metadata --workspace books/<book-slug> --translated-title "<translated_title>" --translated-author "<translated_author>"
     ```

### Step 2: Query Sequential Progress and Next Target
Check overall translation progress and fetch the exact next pending chapter ID:
```bash
$env:PYTHONUTF8=1
uv run python main.py show-translation-progress --workspace books/<book-slug>
```
* **If completed:** If the response says `"all chapter translations completed"`, print the progress and announce successful book completion!
* **If blocked:** If the response is blocked due to preceding ordering gaps, stop and report the gap to the user for repair.
* **If pending:** Parse the JSON payload from the command's reason field to get:
  * `chapter_id`: 1-based sequential integer
  * `slug`: chapter URL friendly identifier
  * `original_title`: raw Chinese title

### Step 3: Fetch Translation Context
Prepare the context paths and continuity indicators for the current chapter:
```bash
$env:PYTHONUTF8=1
uv run python main.py prepare-translation-context --workspace books/<book-slug> --chapter-id <chapter_id>
```
Parse the JSON payload from the reason field to retrieve:
* `raw_path`: path to the raw Chinese file
* `style_path`: path to the style guidelines (`style.yaml`)
* `glossary_path`: path to the dictionary database (`glossary.yaml`)
* `prev_translation_path`: path to Chapter `N-1`'s translation, or `null` if fallback is active (e.g. Chapter 1 or missing files)
* `is_fallback`: `true`/`false`
* `fallback_reason`: description if fallback is active

### Step 4: Resolve Absolute Paths
Before invoking the subagent, you must construct the absolute file paths for all input and output files by resolving their paths relative to the project root (using Python or PowerShell). This ensures the subagent can load and write files reliably regardless of its execution directory.

For example, staging paths should resolve to:
* `staged_txt`: `[Absolute path to staging/chuong-{chapter_id:04d}-staged.txt]`
* `staged_yaml`: `[Absolute path to staging/chuong-{chapter_id:04d}-proposals.yaml]`

### Step 5: Spawn the Isolation Subagent Natively
Spawn a specialized translation subagent natively using the `invoke_subagent` tool. Do NOT attempt to run external python scripts or curl commands targeting third-party LLM APIs (OpenRouter, OpenAI, etc.). Use exactly this structure:

```json
invoke_subagent({
  "Subagents": [
    {
      "Prompt": "[Subagent Prompt]",
      "Role": "Chinese-to-Vietnamese Xianxia/Tu Chan Translator",
      "TypeName": "ag_translator"
    }
  ]
})
```

The prompt payload passed to the subagent must match the following template, replacing all bracketed `[Absolute Path to ...]` placeholders with the resolved absolute paths:

```markdown
Please translate the assigned chapter.

## Inputs
- raw_path: [Absolute Path to raw_path]
- style_path: [Absolute Path to style_path]
- glossary_path: [Absolute Path to glossary_path]
- prev_translation_path: [Absolute Path to prev_translation_path]
- staged_txt: [Absolute Path to staging/chuong-{chapter_id:04d}-staged.txt]
- staged_yaml: [Absolute Path to staging/chuong-{chapter_id:04d}-proposals.yaml]
- chapter_id: [chapter_id]
```

### Step 6: Lightweight Staging Verification
Once the subagent returns a successful status, the Main Agent must verify the file was written correctly. To prevent context window overload:
* Run `view_file` reading **only the first 3 lines** of the staged file `books/<book-slug>/staging/chuong-{chapter_id:04d}-staged.txt`.
* Confirm that the first line contains the correct `# [title_vi]` format.
* Confirm that the character count matches expectations and the file is not empty.

### Step 7: Atomically Promote the Output
Once the staging files are verified, invoke the CLI promotion subcommand:
```bash
$env:PYTHONUTF8=1
uv run python main.py promote-chapter --workspace books/<book-slug> --chapter-id <chapter_id>
```
Confirm the command returns `status: ok`. This validates the staging files, moves the translation atomically to the `translations/` directory, merges any staged glossary proposals, updates `state.yaml` with hashes, and cleans up the staging files.

### Step 8: Retries, Backoffs, and Resumption
* **Transient Failures:** If the subagent fails or the promotion is blocked, retry the chapter up to **3 times**. Run a polite backoff before each retry.
* **Exhausted Retries:** If a chapter fails all 3 attempts, halt execution immediately. Print a detailed error report. Leave the workspace clean at the last successful checkpoint so that the run can be resumed later.
* **Loop:** If promotion is successful, repeat from Step 2.

---

## Common Pitfalls

* **Main Agent Context Overload:** Reading raw or complete translations in your main session immediately floods your token window. Keep all file-level reads locked inside the isolation subagent.
* **Bypassing Lexical Sandbox:** Leaving modern English conjunctions ("but", "while") or articles ("the") in classical Xianxia/Tu Chan Vietnamese prose. Always enforce the Lexical Sandbox mapping table check.
* **Incorrect Metadata Updates:** Trying to manually search/replace inside `book.json` or `state.yaml`. Always use the CLI commands (`promote-chapter`, etc.) to update metadata.
* **Using External LLM APIs:** Attempting to use Python or shell scripts to send raw text to external APIs (OpenAI, OpenRouter, etc.) instead of spawning a subagent. This is strictly prohibited and bypasses the native orchestration framework. Always use `invoke_subagent`.

<!--
Honesty contracts for tests:
books/<book-slug>/
reports/results/
not implemented by Phase 1
-->
