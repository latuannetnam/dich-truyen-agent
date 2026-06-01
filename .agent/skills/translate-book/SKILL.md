---
name: "translate-book"
description: "Translate an approved novel workspace sequentially"
metadata:
  short-description: "Translate an approved novel workspace sequentially"
---

# Translate Book (Sequential Agent Orchestration Mode)

## Overview

Translate crawled and approved Chinese chapters sequentially using context-isolated translator subagents. The Main Agent acts as a lightweight coordinator, looping through pending chapters, querying translation contexts, dispatching specialized subagents to perform Socratic translation, and atomically promoting the outputs. This prevents raw text files or massive translations from flooding the Main Agent's context window, ensuring high token efficiency and consistent pronoun (xưng hô) continuity.

> [!IMPORTANT]
> **Context Protection & Sequential Execution:**
> Do **NOT** read raw source Chinese files or complete Vietnamese chapters into your own Main Agent session. Spawning subagents keeps your context window clear and allows translating hundreds of chapters continuously. 
> Chapters are translated **strictly in order** so that each chapter `N` can receive the completed Vietnamese translation of chapter `N-1` as narrative context.

---

## Core Workflow

### Step 1: Verify the Crawl gate Checkpoint
Enforce that the workspace has an active and valid `crawl-approved` checkpoint before proceeding:
```bash
uv run python main.py check-gate --workspace books/<book-slug> --type crawl-approved
```
If this command blocks, stop the workflow and guide the user to review and approve the crawled raw contents first.

### Step 2: Query Sequential Progress and Next Target
Check overall translation progress and fetch the exact next pending chapter ID:
```bash
uv run python main.py show-translation-progress --workspace books/<book-slug>
```
- **If completed:** If the response says `"all chapter translations completed"`, print the progress and announce successful book completion!
- **If blocked:** If the response is blocked due to preceding ordering gaps, stop and report the gap to the user for repair.
- **If pending:** Parse the JSON payload from the command's reason field to get:
  - `chapter_id`: 1-based sequential integer
  - `slug`: chapter URL friendly identifier
  - `original_title`: raw Chinese title

### Step 3: Fetch Translation Context
Prepare the absolute file paths and continuity indicators for the current chapter:
```bash
uv run python main.py prepare-translation-context --workspace books/<book-slug> --chapter-id <chapter_id>
```
Parse the JSON payload from the reason field to retrieve:
- `raw_path`: absolute path to the raw Chinese file
- `style_path`: absolute path to the style guidelines (`style.yaml`)
- `glossary_path`: absolute path to the dictionary database (`glossary.yaml`)
- `prev_translation_path`: absolute path to Chapter `N-1`'s translation, or `null` if fallback is active (e.g. Chapter 1 or missing files)
- `is_fallback`: `true`/`false`
- `fallback_reason`: description if fallback is active

### Step 4: Spawn the Isolation Subagent
Spawn a specialized translation subagent using the `invoke_subagent` (or equivalent Antigravity subagent invocation) tool using this exact prompt payload, replacing bracketed parameters `[...]` with the resolved context paths:

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
   * Before writing the file, you must explicitly scan your entire draft translation for common leaked English words (such as: `but`, `here`, `now`, `okay`, `the`, `and`, `or`, `while`, `before`, `after`, `of`, `to`, `in`, `on`, `at`, `for`, `with`). If any are found, immediately replace them with their proper Vietnamese equivalents.
   * **No Chinese Residue:** The translated narrative body MUST consist solely of natural Vietnamese prose. You must NEVER output original Chinese characters, bilingual annotations (e.g., `中文 (tiếng Việt)`), or translator notes inside the body of `chuong-{chapter_id:04d}-staged.txt`. All Chinese term proposals must be strictly isolated to the separate `proposals.yaml` file.
5. **Write Target Files:** 
   * **Staged Translation:** Write the complete translated Vietnamese text directly to `[Absolute Path to staging/chuong-{chapter_id:04d}-staged.txt]`.
     * **Title Formatting:** The very first line of this file must contain the translated chapter title, formatted exactly as `# [title_vi]` (e.g., `# Chương 1715 Thiên Ma Truyền Thuyết`).
     * Ensure there is a blank line immediately after this first line.
   * **Staged Glossary Proposals:** If you find new Chinese names, factions, items, or terms that are missing from `glossary.yaml` and had to be translated, write a staged proposals YAML file directly to `[Absolute Path to staging/chuong-{chapter_id:04d}-proposals.yaml]` containing structured dictionary entries:
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

Return a JSON block summarizing:
{
  "status": "success",
  "chapter_id": [Chapter ID],
  "title_vi": "[Translated Vietnamese Title]",
  "character_count": [Count],
  "proposals_count": [Count]
}
```

### Step 5: Atomically Promote the Output
Once the subagent returns a successful JSON status, invoke the CLI promotion subcommand:
```bash
uv run python main.py promote-chapter --workspace books/<book-slug> --chapter-id <chapter_id>
```
Confirm the command returns `status: ok`. This validates the staging files, moves the translation atomically, merges the glossary proposals, updates `state.yaml` with hashes, and cleans the staging files.

### Step 6: Retries, Backoffs, and Resumption
- **Transient Failures:** If a subagent call fails or the promotion is blocked, retry the chapter up to **3 times**. Run a polite backoff before each retry.
- **Exhausted Retries:** If a chapter fails on all 3 attempts, halt execution immediately. Print a detailed error report pointing to `reports/results/promote-chapter.yaml` or staging logs. Leave the workspace clean at the last successful checkpoint. This allows the user to inspect, manually edit the staged text or glossary, and run the skill again to resume safely from the failed chapter.
- **Loop:** If promotion is successful, repeat from Step 2.

---

## Common Pitfalls
* **Context Overload:** Reading raw or complete translations in your main session immediately floods your token window. Keep all file-level reads locked inside the isolation subagent.
* **Leaked Conjunctions:** Forgetting the Lexical Sandbox check, which introduces modern English conjunctions ("but", "while") into classical XianxiaTu Chân Vietnamese prose.
* **Proposals Format:** Generating a flat key-value dictionary for proposals instead of the structured schema containing translation, category, and source. Always follow the Pydantic structured glossary contract.

<!-- not implemented by Phase 1 books/<book-slug>/ -->
