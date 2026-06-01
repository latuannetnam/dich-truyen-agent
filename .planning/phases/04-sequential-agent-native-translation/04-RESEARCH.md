# Phase 4: Sequential Agent-Native Translation - Research

**Researched:** 2026-06-01
**Domain:** Sequential translation worker protocol, context building, staging contracts, atomic promotion CLI helpers, and skill-driven retry orchestration loop.
**Confidence:** HIGH

## Summary

Phase 4 establishes the sequential translation engine for Dich Truyen Agent. This phase enforces that translation refuses to start unless a `crawl-approved` checkpoint is active, spawns isolated subagents to translate chapter by chapter, passes immediate predecessor Vietnamese text as narrative context (with safe fallback for the first chapter or reset points), stages all translations and glossary proposals to prevent half-written work from corrupting the workspace, provides a CLI command to atomically promote completed translations, and defines a robust skill-driven loop in the `$translate-book` skill to handle retries and halts safely.

---

## Recommended Architecture

### 1. Context Preparation Helper (`src/dich_truyen_agent/translate_worker.py` or `workspace.py`)

To implement **Context Preparation (D-01, D-04)**, the CLI will expose a command `prepare-translation-context` that outputs a lightweight JSON block.
* Function: `prepare_translation_context(workspace_root: Path, chapter_id: int) -> OperationResult`
* Behavior:
  1. Verifies that the `crawl-approved` checkpoint is present and current.
  2. Identifies the chapter in the `ChapterCatalog` and `BookState`.
  3. Ensures all previous chapters are `COMPLETED` in their translation status (continuity rule).
  4. Identifies the input paths:
     - `raw_path`: `raw/chuong-{chapter_id:04d}-...txt`
     - `style_path`: `style.yaml`
     - `glossary_path`: `glossary.yaml`
     - `prev_translation_path`: `translations/chuong-{chapter_id-1:04d}-...txt` if `chapter_id > 1`.
  5. **Fallback Rule:** If `chapter_id == 1` or if the predecessor file `translations/chuong-{chapter_id-1:04d}-...txt` is missing/unreadable, the helper sets `prev_translation_path` to `null` and adds a note field: `"is_first_chapter": true` or `"missing_predecessor": true`.
  6. Returns `OperationResult` with the JSON payload of absolute paths.

### 2. Subagent Prompt & Protocol (`.agent/skills/translate-book/SKILL.md`)

* Spawns an isolated translation subagent using the standard prompt template modeled after the successful `translate-error-chapters` pattern:
  - **Inputs:** Absolute paths to Raw Chinese File, Style Guidelines, Glossary, and Previous Vietnamese Translation (if available).
  - **Instructions:**
    - Read the files using `view_file`.
    - Translate the chapter title following standard Xianxia title formats (e.g. `Chương [N] [Capitalized Title]`).
    - Translate the chapter body cleanly.
    - **Lexical Sandbox Rule:** programmatically clean common leaked English words (e.g. `but`, `the`, `and`, `or`, `while`).
    - Write translated Vietnamese text directly to `staging/chuong-{chapter_id:04d}-staged.txt`. First line formatted as `# Chương [N] [Title]`.
    - Write proposed new glossary terms (Chinese -> translation, category, note) to `staging/chuong-{chapter_id:04d}-proposals.yaml`.
  - **Output Format:** JSON returning success/error status, character count, and proposed terms count.

### 3. Staging and Atomic Promotion Helper (`src/dich_truyen_agent/workspace.py`)

To implement **Staging and Atomic Promotion (D-02)**:
* Function: `promote_chapter_translation(workspace_root: Path, chapter_id: int) -> OperationResult`
* Behavior:
  1. Validates that `staging/chuong-{chapter_id:04d}-staged.txt` exists and is not empty.
  2. Ensures the text has minimum length (e.g., matching or proportional to raw size).
  3. Validates the existence and syntax of `staging/chuong-{chapter_id:04d}-proposals.yaml`.
  4. Moves the staged text atomically to `translations/<canonical_filename>` (resolving name from `ChapterCatalog`).
  5. Merges proposals from `staging/chuong-{chapter_id:04d}-proposals.yaml` using `merge_glossary_proposals()` which automatically handles snapshotting and conflict reporting.
  6. Calculates the SHA-256 hash of the promoted translation file.
  7. Updates `state.yaml` to mark the chapter's `translation` status as `COMPLETED`, storing the hash and `canonical_path`.
  8. Deletes the staged files cleanly.
  9. Returns `OperationResult(status=OK)`.

### 4. CLI Subcommands (`src/dich_truyen_agent/cli.py`)

Register the following subcommands in `cli.py`:
* `prepare-translation-context`: Calls `prepare_translation_context()`.
* `promote-chapter`: Calls `promote_chapter_translation()`.

### 5. Skill Orchestration Loop (`.agent/skills/translate-book/SKILL.md`)

- Driven by the Antigravity agent in the `$translate-book` skill:
  - Loop starts at the first chapter with `translation` stage in `PENDING` state.
  - Prepares context, invokes the translator subagent.
  - Promotes the chapter.
  - **Retries:** If the subagent fails, retry up to 3 times, executing a brief backoff.
  - If retries fail, halt completely, reporting the failure so the user can fix the issue in `staging/` or `glossary.yaml` and resume cleanly.

---

## Validation Architecture

We will implement isolated unit and integration tests under `tests/test_translation.py` to verify:

| Requirement | Automated Coverage |
|-------------|--------------------|
| **TRAN-01** | Test that translation context generation blocks if `crawl-approved` checkpoint is absent. |
| **TRAN-02 / TRAN-03** | Verify `prepare-translation-context` accurately resolves paths for raw, style, glossary, and predecessor chapter. |
| **TRAN-04** | Verify atomic promotion flow: validates staged files, copies atomically, merges proposals, updates state, and removes staging files. |
| **TRAN-05** | Verify continuity constraint: preparation blocks if any prior chapter translation is incomplete. |
| **TRAN-06 / TRAN-07** | Verify sequential loop resume safety: if a mid-book chapter fails, state is preserved, and resume picks up exactly at the failed chapter. |

---

## Security & STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-04-01 | Tampering | state updates | mitigate | State updates are written atomically via temp-sibling replacement to prevent corruption during system interrupts. |
| T-04-02 | Information Disclosure | context leak | mitigate | Files are passed as clean local workspace absolute paths rather than streaming raw text through orchestrator context windows. |

---

*Phase: 04-sequential-agent-native-translation*
*Research complete: 2026-06-01*
