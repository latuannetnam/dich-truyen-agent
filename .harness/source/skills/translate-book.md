# {SKILL_TITLE}

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

{TRANSLATE_DISPATCH}

{TRANSLATE_ORCHESTRATION}

---

## Common Pitfalls

* **Main Agent Context Overload:** Reading raw or complete translations in your main session immediately floods your token window. Keep all file-level reads locked inside the isolation subagent.
* **Verbose Long-Book Summaries:** Returning cumulative chapter lists across hundreds of batches will exhaust the Main Agent context. Use compact batch counters and re-query CLI state.
* **Bypassing Lexical Sandbox:** Leaving modern English conjunctions ("but", "while") or articles ("the") in classical Xianxia/Tu Chan Vietnamese prose. Always enforce the Lexical Sandbox mapping table check.
* **Incorrect Metadata Updates:** Trying to manually search/replace inside `book.json` or `state.yaml`. Always use the CLI commands (`promote-chapter`, etc.) to update metadata.
* **Using External LLM APIs:** Attempting to use Python or shell scripts to send raw text to external APIs (OpenAI, OpenRouter, etc.) instead of spawning a subagent. This is strictly prohibited and bypasses the native orchestration framework.
