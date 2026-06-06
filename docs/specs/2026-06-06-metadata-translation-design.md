# Metadata Translation Design

## Overview
The goal is to export ebooks (EPUB, AZW3, etc.) containing the translated Vietnamese book title and author name, rather than the raw Chinese text. 

To maintain the architectural pattern of isolated subagents and deterministic CLI commands, the Main Agent orchestrating `translate-book` will check if metadata translation is complete. If not, it will spawn a specialized short-lived subagent to translate the title and author, then save the results using a new deterministic CLI command.

## Architecture

### 1. Data Models (`models.py`)
Add two optional fields to `BookMetadata`:
```python
translated_title: str | None = None
translated_author: str | None = None
```

### 2. Deterministic CLI (`cli.py`, `workspace.py`)
Introduce a new CLI command: `update-book-metadata`
```bash
uv run python main.py update-book-metadata \
    --workspace books/<book-slug> \
    --translated-title "<translated title>" \
    --translated-author "<translated author>"
```
This command will load `book.yaml`, update the new fields, and atomically save the file.

### 3. Translation Orchestration (`translate-book` & `oc-translate-book` Skills)
Insert a new Step 1.5 into the orchestration workflow:

**Step 1.5: Metadata Translation**
- The Main Agent reads `book.yaml` directly or uses a command to inspect the workspace.
- If `translated_title` or `translated_author` are missing or empty:
  - Spawn a native subagent (`metadata_translator` role) to translate the raw Chinese title and author into Vietnamese (applying Xianxia/Tu Chan style).
  - The subagent returns JSON with `translated_title` and `translated_author`.
  - The Main Agent invokes the `update-book-metadata` CLI command to persist these translations.

### 4. Export Artifacts (`export.py`, `export-book` Skill)
Update the `compile_epub_in_memory` function to use `book_metadata.translated_title` and `book_metadata.translated_author`. If the translated fields are missing, it will gracefully fall back to the original Chinese `title` and `author`.

## Error Handling & Edge Cases
- **Missing Author:** Some books might not have an author. The subagent should handle `None` gracefully and return `null` or a placeholder.
- **Failures:** If the `metadata_translator` subagent fails or times out, the Main Agent can retry once or twice, similar to chapter translations.
- **Backwards Compatibility:** Existing workspaces without `translated_title` in `book.yaml` will deserialize properly because the new fields default to `None`.

## Security & Constraints
- No external Python scripts making direct LLM API calls are permitted. All translation MUST go through native `invoke_subagent` capabilities.
- `book.yaml` updates MUST be performed via the deterministic CLI command to prevent file corruption.
