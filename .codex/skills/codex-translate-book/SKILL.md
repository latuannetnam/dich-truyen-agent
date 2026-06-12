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

> [!IMPORTANT]
> **Compact Long-Book Automation:**
> Use the shared configurable batch size for every harness. The default is 5 chapters and can be overridden with `DICH_TRUYEN_TRANSLATION_BATCH_SIZE` in the project `.env` file. For 1000+ chapter books, repeat fresh compact batches until completion. Do not accumulate promoted chapter arrays, raw text, completed translation text, or verbose per-chapter logs in the Main Agent context.

Effective translation settings are loaded with:
```bash
$env:PYTHONUTF8=1
uv run python main.py show-translation-settings --json
```

Explicit runtime arguments override `.env`; `.env` overrides the built-in default of 5.

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
  prompt="Execute the compact translation loop for the next <batch_size> pending chapters sequentially, where <batch_size> comes from show-translation-settings data.batch_size unless the user supplied an explicit override. For each chapter, fetch next-translation-work-item, spawn codex_translator, verify staging through verify-staged-chapter, and promote. Return only {status, processed_count, chapter_start, chapter_end, next_chapter_id, failure_reason}."
)
```

This path must use native Codex subagent delegation only, never external LLM APIs.

### Step 2: Load Effective Batch Size
Fetch translation settings before dispatching a coordinator:
```bash
$env:PYTHONUTF8=1
uv run python main.py show-translation-settings --json
```
Use `data.batch_size` unless the user supplied an explicit runtime override. The built-in default is 5.

### Step 3: Fetch Progress and Dispatch Compact Coordinator
The Main Agent fetches the next deterministic work item:
```bash
$env:PYTHONUTF8=1
uv run python main.py next-translation-work-item --workspace books/<book-slug> --json
```
* **If completed:** Report book completion with compact counts only.
* **If blocked:** Stop and report the gap to the user for repair.
* **If pending:** The Main Agent spawns a **Coordinator Subagent** to handle the next `batch_size` pending chapters using the harness-native dispatch block above.

> [!IMPORTANT]
> **Enforced Stateless Iteration:**
> 1. **Strict Batch Limit:** You must NEVER instruct a single Coordinator to translate the entire book. You must always specify the effective `batch_size` in your prompt.
> 2. **Fresh Instances:** When the Coordinator completes its batch, you must spawn a completely NEW Coordinator instance. Do not send follow-up instructions to the previous subagent.
> 3. **Loop:** Repeat this cycle of spawning fresh Coordinators until `next-translation-work-item` returns `completed`.
> 4. **Compact Output:** Do not accumulate chapter arrays in the Main Agent. Re-query CLI state after each batch.

### Step 4: The Coordinator Micro-Loop
**The following steps (4 to 8) are executed purely by the Coordinator Subagent.**
Inside the Coordinator, fetch the exact next pending work item:
```bash
$env:PYTHONUTF8=1
uv run python main.py next-translation-work-item --workspace books/<book-slug> --json
```
Parse `data`. Stop on `completed`, `blocked`, or `error`.

### Step 5: Spawn the Translator Subagent (Coordinator)
The Coordinator spawns the Translator subagent using the harness-native mechanism in the dispatch block, passing the absolute paths reported by `next-translation-work-item`, including `glossary_context_path`.

### Step 6: Lightweight Staging Verification (Coordinator)
The Coordinator runs structural verification through the CLI:
```bash
$env:PYTHONUTF8=1
uv run python main.py verify-staged-chapter --workspace books/<book-slug> --chapter-id <chapter_id> --json
```
This does not replace glossary validation.

### Step 7: Atomically Promote and Loop (Coordinator)
The Coordinator promotes the chapter:
```bash
$env:PYTHONUTF8=1
uv run python main.py promote-chapter --workspace books/<book-slug> --chapter-id <chapter_id> --json
```
If successful, the Coordinator loops back to Step 4 until its assigned batch limit is reached.
If promotion is blocked by glossary consistency, retry the same chapter and include the `promote-chapter` reason in the translator prompt so the next attempt uses the existing glossary mapping and avoids rejected aliases.
* **Retries:** Coordinator retries failures up to 3 times with polite backoffs before halting.

### Step 8: Compact Coordinator Result
Return only `{status, processed_count, chapter_start, chapter_end, next_chapter_id, failure_reason}`. Do not return cumulative chapter lists or per-chapter logs.

---

## Common Pitfalls

* **Main Agent Context Overload:** Reading raw or complete translations in your main session immediately floods your token window. Keep all file-level reads locked inside the isolation subagent.
* **Verbose Long-Book Summaries:** Returning cumulative chapter lists across hundreds of batches will exhaust the Main Agent context. Use compact batch counters and re-query CLI state.
* **Bypassing Lexical Sandbox:** Leaving modern English conjunctions ("but", "while") or articles ("the") in classical Xianxia/Tu Chan Vietnamese prose. Always enforce the Lexical Sandbox mapping table check.
* **Incorrect Metadata Updates:** Trying to manually search/replace inside `book.json` or `state.yaml`. Always use the CLI commands (`promote-chapter`, etc.) to update metadata.
* **Using External LLM APIs:** Attempting to use Python or shell scripts to send raw text to external APIs (OpenAI, OpenRouter, etc.) instead of spawning a subagent. This is strictly prohibited and bypasses the native orchestration framework.
