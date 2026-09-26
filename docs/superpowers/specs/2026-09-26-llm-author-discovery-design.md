# LLM-Driven Novel Author Discovery and Metadata Translation Design

**Date:** 2026-09-26  
**Status:** Approved  
**Author:** Antigravity Team  

---

## 1. Executive Summary

When creating novel workspaces automatically from source URLs (via `orchestrate --url <url>` or `init-book`), novel authors are frequently omitted from CLI arguments. Hardcoding regex patterns to scrape author names across various novel catalog layouts is fragile, unmaintainable, and fails across distinct Chinese novel hosting platforms (e.g. `作者：...`, `xxx 著`, `文 / xxx`, table cells, or metadata headers).

This design upgrades the orchestrator and the native Antigravity metadata agent (`ag_metadata_translator`) to perform **context-aware author discovery using natural language LLM understanding**, without any hardcoded author regex patterns.

---

## 2. Problem Statement

1. **Missing Author in Auto-Discovery:** Currently, `_discover_title` in `orchestrator.py` only extracts the novel title from the `<title>` HTML tag. The `author` field defaults to `"Unknown"` when `--author` is not supplied on the CLI.
2. **Fragile Regex Anti-Pattern:** Regex scraping of author names fails across varied novel websites due to HTML variations, inconsistent spacing, and dynamic catalog structures.
3. **Restricted Agent Scope:** The existing `ag_metadata_translator` definition only translates already-known titles and authors into Vietnamese. If the author is `"Unknown"`, it translates it to `"Khuyết Danh"` without attempting to discover the actual author from the source catalog.
4. **Token Protection Constraint:** The Main Agent must never load full catalog HTML pages or chapter files into its own session. Bounded file handoff to an isolated subagent is strictly required.

---

## 3. Architecture & Data Flow

```
                      +-----------------------------+
                      |   Crawl Phase (Crawler)     |
                      | Downloads index page        |
                      +--------------+--------------+
                                     |
                                     v
                      +-----------------------------+
                      | Extract bounded catalog     |
                      | intro text (< 3,000 chars,  |
                      | stripping chapter links)    |
                      +--------------+--------------+
                                     |
                                     v
                      +-----------------------------+
                      | Save to:                    |
                      | reports/catalog_intro.txt   |
                      +--------------+--------------+
                                     |
                                     v
+------------------------------------+------------------------------------+
| Orchestrator Metadata Node (metadata_node)                              |
| - Checks book.yaml: needs_translation OR author in (None, "", "Unknown")|
| - Prepares prompt with path to reports/catalog_intro.txt                |
+------------------------------------+------------------------------------+
                                     |
                                     v
+------------------------------------+------------------------------------+
| Native Worker: ag_metadata_translator                                  |
| 1. Reads catalog_intro.txt (via Read tool) if author is 'Unknown'       |
| 2. Uses LLM comprehension to identify Chinese author name               |
| 3. Translates title and author into elegant literary Vietnamese        |
| 4. Writes updated author, translated_title, translated_author           |
|    directly into book.yaml                                              |
| 5. Returns compact JSON result                                          |
+------------------------------------+------------------------------------+
                                     |
                                     v
+------------------------------------+------------------------------------+
| Orchestrator Verification                                               |
| - Reloads book.yaml, verifies translated_title is present               |
| - Unblocks transition to chapter translation                            |
+-------------------------------------------------------------------------+
```

---

## 4. Detailed Component Design

### 4.1. Catalog Intro Extraction (`crawl_batch.py`)

During the crawl phase or title discovery:
- Add helper function `extract_catalog_intro(html_content: str, max_chars: int = 3000) -> str`.
- Strips `<script>`, `<style>`, `<link>`, comments, and elements matching `profile.index.chapter_link_selector`.
- Extracts clean introductory text up to `max_chars` characters, containing novel title, author line, tags, synopsis/intro, and metadata.
- Writes to `reports/catalog_intro.txt` in the novel workspace.
- **Fail-safe:** If extraction fails or yields empty text, `reports/catalog_intro.txt` is simply omitted or left empty; the pipeline continues without failure.

### 4.2. Upgraded Agent Persona (`.harness/source/agents/metadata-translator.md`)

Update the source definition of `metadata-translator.md`:
- **Role:** Novel Metadata Analyst and Translator.
- **Tools:** `Read`, `Write`, `Glob`, `Grep`.
- **Inputs provided in prompt:**
  - `book.yaml` absolute path.
  - `Source title`.
  - `Source author` (or `"Unknown"`).
  - Optional `catalog_intro_path` (when source author is `"Unknown"` or missing).
- **Procedure:**
  1. If `Source author` is `"Unknown"`, open `catalog_intro_path` using `Read` tool. Identify the author's Chinese name from context without assuming any fixed regex or keyword format.
  2. If the author is genuinely absent from the catalog text, keep `author: Unknown`.
  3. Translate Chinese title into elegant Sino-Vietnamese (Title Case).
  4. Translate Chinese author into elegant Sino-Vietnamese (Title Case); if author is `"Unknown"`, use `"Khuyết Danh"`.
  5. Update `book.yaml` with the resolved `author`, `translated_title`, and `translated_author`.
  6. Return a clean JSON outcome block.

### 4.3. Harness Synchronization (`tools/sync_harness_adapters.py`)

- Synchronize `.harness/source/agents/metadata-translator.md` to `.agent/agents/ag_metadata_translator.md`.
- Ensure tests in `test_harness_generator_check.py` and `test_harness_adapter_discovery.py` remain fully compliant.

### 4.4. Orchestrator Graph Node (`src/dich_truyen_agent/orchestrator/graph.py`)

Modify `metadata_node`:
1. **Trigger Condition:**
   ```python
   author_unresolved = not metadata.author or metadata.author.strip() in ("", "Unknown")
   needs_translation = (
       not metadata.translated_title
       or author_unresolved
       or not metadata.translated_author
   )
   ```
2. **Prompt Construction:**
   - If `author_unresolved` and `paths.reports / "catalog_intro.txt"` exists, supply `Catalog intro context path: {paths.reports / 'catalog_intro.txt'}`.
   - Instruct the agent to read `catalog_intro.txt`, extract the Chinese author name, translate both fields, and update `book.yaml`.
3. **Post-execution Verification:**
   - Reload `metadata = load_yaml_model(paths.book, BookMetadata)`.
   - Assert `metadata.translated_title` is non-empty. If empty, block with error.
   - If `author` was updated from `"Unknown"` to a valid Chinese name, record diagnostic log.
   - If `author` remains `"Unknown"` (unlisted on source website), accept `translated_author: Khuyết Danh` and proceed to translation phase without blocking.

---

## 5. Security, Token & Performance Guardrails

1. **Token Protection:**
   - The Main Agent orchestrator session never reads `catalog_intro.txt`.
   - The file size is strictly capped at 3,000 characters, consuming fewer than 1,000 tokens in the worker subagent context.
2. **Execution Efficiency:**
   - Author extraction and metadata translation occur in a single `ag_metadata_translator` CLI process invocation, avoiding extra subagent startup latency (~15–20s saved).
3. **No External LLM APIs:**
   - Only the native Antigravity worker subprocess is used, strictly obeying project guardrails.

---

## 6. Testing Strategy

1. **Unit Tests for Catalog Intro Extraction:**
   - Verify `extract_catalog_intro` strips link catalogs and preserves introductory/metadata text.
   - Verify handling of truncated or malformed HTML.
2. **Unit Tests for `metadata_node` Prompt & Verification:**
   - Verify prompt includes `catalog_intro_path` when `author` is `"Unknown"`.
   - Verify prompt omits `catalog_intro_path` when `author` is already explicitly provided.
   - Verify `book.yaml` update with extracted author is correctly preserved and loaded.
3. **Harness Sync Verification:**
   - Run `python tools/sync_harness_adapters.py --check` to guarantee adapter consistency.
4. **Full Test Suite:**
   - Ensure all existing 607+ tests continue to pass.
