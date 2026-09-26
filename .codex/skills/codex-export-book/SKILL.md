---
name: codex-export-book
description: "Use when running the export-book phase of the Chinese-to-Vietnamese novel translation pipeline in the codex harness."
---

<!-- GENERATED from .harness/source by tools/sync_harness_adapters.py. Do not edit directly. -->

# Codex-Export Book

Thin compatibility entrypoint for the ebook export phase of the novel translation pipeline. Maps directly to the shared orchestrator with `--start-at export --stop-after export`.

## Workflow

1. **Execute Ebook Export**:
   Run export through the orchestrator:
   ```powershell
   $env:PYTHONUTF8=1
   uv run python main.py orchestrate --workspace books/<book-slug> --start-at export --stop-after export [--formats epub,azw3]
   ```
   - Verifies the `qa-approved` checkpoint before compiling.
   - Compiles canonical EPUB and AZW3 to `books/<book-slug>/exports/`.
   - Requires `DICH_TRUYEN_EPUBCHECK_PATH` for EPUB validation.
   - Derivative formats require `DICH_TRUYEN_CALIBRE_PATH`.

2. **Handle Errors or Missing Prerequisites**:
   - If QA gate is missing or invalid, run QA first via `check-translation`.
   - Inspect export results in `books/<book-slug>/reports/results/export-book.yaml`.

See the orchestrate-book skill for full parameter reference and resume workflows.
