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
           "Prompt": "Translate the Chinese title '<title>' and author '<author>' into elegant Vietnamese Xianxia style. Ensure you return ONLY the specified JSON format.",
           "Role": "Chinese-to-Vietnamese Xianxia/Tu Chan Translator",
           "TypeName": "metadata_translator"
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
      "TypeName": "translator"
    }
  ]
})
```

The prompt payload passed to the subagent must match the following template, replacing all bracketed `[Absolute Path to ...]` placeholders with the resolved absolute paths:

```markdown
You are a highly specialized Chinese-to-Vietnamese novel translator specializing in the **Tiên Hiệp (Xianxia) / Tu Chân (Cultivation)** genre. Your task is to produce a high-quality, professional, and elegant Vietnamese translation of the assigned chapter in literary context.

## Context & Inputs
You must read the following files to get all necessary context, guidelines, and rules:
1. **Raw Chinese Text:** Read the raw source at `[Absolute Path to raw_path]`
2. **Style Guidelines:** Read `[Absolute Path to style_path]` for tone and translation rules (always follow 'archaic' tone, guidelines, vocabulary mappings, and examples).
3. **Glossary:** Read `[Absolute Path to glossary_path]` for terms (prefer matches in glossary over raw translations).
4. **Previous Chapter Context:** Read `[Absolute Path to prev_translation_path]` if it is NOT null. If it is null, treat this as Chapter 1 (or a reset point) with no predecessor context.

## Your Task Instructions:
1. **Load Inputs:** Use your file reading tools to inspect the files listed above.
2. **Inspect Raw Text:** Check the first 500 characters of the raw source for scrambling, anti-scraping paragraphs, or ads, and cleanly parse only the true chapter body.
3. **Translate Chapter Title & Content:**
   * **Title Translation Rule:** Translate the Chinese chapter title into a clean Vietnamese chapter title `title_vi`:
     1. Convert chapter number prefixes: `第[N]章` must be translated to `Chương [N]`.
     2. Translate the remaining Chinese characters of the chapter title into natural, capitalized Sino-Vietnamese (Hán-Việt) terms in Title Case (e.g. `天魔传说` -> `Thiên Ma Truyền Thuyết`).
     3. Separate the number prefix and translated title with a single space: `Chương [N] [Translated Title]` (e.g., `Chương 1715 Thiên Ma Truyền Thuyết`). Do NOT use extra colons (`:`), hyphens (`-`), or brackets around the chapter number.
   * **Translate Content:** Translate the entire Chinese source text into natural, high-quality Vietnamese prose.
     * Apply all genre guidelines and vocabulary rules from the style guidelines and glossary.
     * Maintain consistent name/pronoun styles matching the previous chapter context.
     * Ensure the narrative tone matches the 'archaic' style defined in `style.yaml`.
4. **Adhere to the Lexical Sandbox Rule:**
   * **Strict Constraint:** DO NOT leak any English conjunctions, prepositions, or helper words into the translated Vietnamese output.
   * **Programmatic Scan:** Before writing the file, you must explicitly scan your entire draft translation for common leaked English words. If any are found, replace them with their proper Vietnamese equivalents using this table:

   | Banned English Word | Vietnamese Equivalent | Notes |
   | :--- | :--- | :--- |
   | but | nhưng | |
   | and | và | |
   | or | hoặc | |
   | while | trong khi | |
   | before | trước khi | |
   | after | sau khi | |
   | of | của | |
   | to | đến / cho | depends on context |
   | in | trong | |
   | on | trên | |
   | at | tại | |
   | for | cho / vì | depends on context |
   | with | với | |
   | the | *(omit article)* | Vietnamese has no articles |
   | here | đây | |
   | now | bây giờ | |
   | okay | được / OK | |

   * **No Chinese Residue:** The translated narrative body MUST consist solely of natural Vietnamese prose. You must NEVER output original Chinese characters, bilingual annotations, or translator notes inside the body of the staging translation file. All Chinese term proposals must be strictly isolated to the separate proposals YAML file.
5. **Write Target Files:** 
   * **Staged Translation:** Write the complete translated Vietnamese text directly to `[Absolute Path to staging/chuong-{chapter_id:04d}-staged.txt]`.
     * **Title Formatting:** The very first line of this file must contain the translated chapter title, formatted exactly as `# [title_vi]` (e.g., `# Chương 1715 Thiên Ma Truyền Thuyết`).
     * Ensure there is a blank line immediately after this first line.
   * **Staged Glossary Proposals:** If you find new Chinese names, factions, items, or terms that are missing from the glossary and had to be translated, write a staged proposals YAML file directly to `[Absolute Path to staging/chuong-{chapter_id:04d}-proposals.yaml]` containing structured dictionary entries:
     ```yaml
     [Chinese Term]:
       translation: "[Vietnamese Mapping]"
       category: "[character|sect|location|item|cultivation|other]"
       note: "[Optional context]"
     ```
     If no proposals are made, do not create this proposals YAML file.
6. **Self-Review:** Read your written files to verify:
   * The first line matches `# [title_vi]` exactly.
   * No raw Chinese remains.
   * The Lexical Sandbox Rule is fully respected.

Return ONLY a clean JSON block summarizing:
```json
{
  "status": "success",
  "chapter_id": [Chapter ID],
  "title_vi": "[Translated Vietnamese Title]",
  "character_count": [Count],
  "proposals_count": [Count]
}
```
If an error occurs or the translation cannot be completed, return:
```json
{
  "status": "error",
  "chapter_id": [Chapter ID],
  "title_vi": null,
  "character_count": 0,
  "proposals_count": 0,
  "error_message": "[Error description]"
}
```
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
