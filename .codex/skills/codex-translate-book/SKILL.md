---
name: codex-translate-book
description: "Use when running the translate-book phase of the Chinese-to-Vietnamese novel translation pipeline in the codex harness."
---

<!-- GENERATED from .harness/source by tools/sync_harness_adapters.py. Do not edit directly. -->

# Codex-Translate Book

## Overview

Translate crawled and approved Chinese chapters sequentially with harness-native isolated translation workers. The workflow protects the Main Agent context window while preserving narrative continuity across chapters.

> [!IMPORTANT]
> **Context Protection & Sequential Execution:**
> Do **NOT** read raw source Chinese files or complete Vietnamese chapters into your own Main Agent session.
> Chapters are translated **strictly in order** so that each chapter `N` can receive the completed Vietnamese translation of chapter `N-1` as narrative context.

> [!WARNING]
> **Strict External API Prohibition:**
> You are strictly forbidden from using external LLM APIs (e.g., OpenRouter, OpenAI, Gemini) via Python scripts, curl, or any other external tool to perform the translation. You MUST only use the native harness subagent capability as specified in the dispatch block for this adapter.

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
1. Read the contents of `books/<book-slug>/book.yaml` using the harness file-reading tool.
2. Check if `translated_title` and `translated_author` are populated.
3. If they are missing or empty, dispatch the specialized metadata translation subagent using the harness-native mechanism in the dispatch block below.
4. Extract `translated_title` and `translated_author` from the subagent's JSON response.
5. Persist the translated metadata to the workspace by running:
   ```bash
   $env:PYTHONUTF8=1
   uv run python main.py update-book-metadata --workspace books/<book-slug> --translated-title "<translated_title>" --translated-author "<translated_author>"
   ```

### Harness-Specific Translation Dispatch

Use `spawn_agent` for native Codex subagent delegation.

Metadata translation uses `codex_metadata_translator`, and chapter translation uses `codex_translator`:
```text
spawn_agent(
  type="codex_coordinator",
  prompt="Execute the translation loop for the next 20 pending chapters sequentially. For each chapter, query progress, prepare context, spawn codex_translator, verify staging, and promote."
)
```

This path must use native Codex subagent delegation only, never external LLM APIs.

### Step 2: Query Progress and Dispatch Coordinator
The Main Agent checks overall translation progress:
```bash
$env:PYTHONUTF8=1
uv run python main.py show-translation-progress --workspace books/<book-slug>
```
* **If completed:** Print the progress and report book completion.
* **If blocked:** Stop and report the gap to the user for repair.
* **If pending:** The Main Agent spawns a **Coordinator Subagent** to handle a batch of pending chapters (e.g., the next 20 chapters) using the harness-native dispatch block above.

> [!IMPORTANT]
> **Enforced Stateless Iteration:**
> 1. **Strict Batch Limit:** You must NEVER instruct a single Coordinator to translate the entire book. You must always specify a strict limit (e.g., 20 chapters) in your prompt.
> 2. **Fresh Instances:** When the Coordinator completes its batch, you must spawn a completely NEW Coordinator instance. Do not send follow-up instructions to the previous subagent.
> 3. **Loop:** Repeat this cycle of spawning fresh Coordinators until the progress check returns "completed".

### Step 3: The Coordinator Micro-Loop
**The following steps (3 to 8) are executed purely by the Coordinator Subagent.**
Inside the Coordinator, query the exact next pending chapter:
```bash
$env:PYTHONUTF8=1
uv run python main.py show-translation-progress --workspace books/<book-slug>
```
Parse the JSON payload to get `chapter_id`.

### Step 4: Fetch Translation Context (Coordinator)
Prepare context paths:
```bash
$env:PYTHONUTF8=1
uv run python main.py prepare-translation-context --workspace books/<book-slug> --chapter-id <chapter_id>
```

### Step 5: Resolve Absolute Paths (Coordinator)
Construct the absolute file paths for all input and output files by resolving their paths relative to the project root.

### Step 6: Spawn the Translator Subagent (Coordinator)
The Coordinator spawns the Translator subagent using the harness-native mechanism in the dispatch block, passing the absolute paths reported by `prepare-translation-context`, including `glossary_context_path`.

### Step 7: Lightweight Staging Verification (Coordinator)
The Coordinator reads only the first 3 lines of `books/<book-slug>/staging/chuong-{chapter_id:04d}-staged.txt` to confirm the `# [title_vi]` format.

### Step 8: Atomically Promote and Loop (Coordinator)
The Coordinator promotes the chapter:
```bash
$env:PYTHONUTF8=1
uv run python main.py promote-chapter --workspace books/<book-slug> --chapter-id <chapter_id>
```
If successful, the Coordinator loops back to Step 3 until its assigned batch limit is reached.
If promotion is blocked by glossary consistency, retry the same chapter and include the `promote-chapter` reason in the translator prompt so the next attempt uses the existing glossary mapping and avoids rejected aliases.
* **Retries:** Coordinator retries failures up to 3 times with polite backoffs before halting.

---

## Common Pitfalls

* **Main Agent Context Overload:** Reading raw or complete translations in your main session immediately floods your token window. Keep all file-level reads locked inside the isolation subagent.
* **Bypassing Lexical Sandbox:** Leaving modern English conjunctions ("but", "while") or articles ("the") in classical Xianxia/Tu Chan Vietnamese prose. Always enforce the Lexical Sandbox mapping table check.
* **Incorrect Metadata Updates:** Trying to manually search/replace inside `book.json` or `state.yaml`. Always use the CLI commands (`promote-chapter`, etc.) to update metadata.
* **Using External LLM APIs:** Attempting to use Python or shell scripts to send raw text to external APIs (OpenAI, OpenRouter, etc.) instead of spawning a subagent. This is strictly prohibited and bypasses the native orchestration framework.
