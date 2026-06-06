# {SKILL_TITLE}

This skill compiles a sequential, QA-approved translation workspace into conformant canonical EPUB and AZW3 ebook formats by default, and derives MOBI and PDF only if explicitly requested.

## CLI Usage

```powershell
# Default: generate canonical EPUB + AZW3 only (enforces QA approval checkpoint)
$env:PYTHONUTF8=1
uv run python -m dich_truyen_agent.cli export-book --workspace books/<book-slug>

# Generate EPUB + AZW3 along with optional derivatives (MOBI, PDF)
$env:PYTHONUTF8=1
uv run python -m dich_truyen_agent.cli export-book --workspace books/<book-slug> --formats epub,azw3,mobi,pdf
```

## System Environment Variables

- `DICH_TRUYEN_EPUBCHECK_PATH`: Path to your `epubcheck.jar` file or installation folder. (EPUBCheck is required to validate canonical EPUB compliance before export completes successfully).
- `DICH_TRUYEN_CALIBRE_PATH`: Path to Calibre's `ebook-convert` executable (optional; if missing, derivative format compilation is skipped with a warning, but canonical EPUB generation completes successfully).

Verify these are set via PowerShell:
```powershell
$env:DICH_TRUYEN_EPUBCHECK_PATH
$env:DICH_TRUYEN_CALIBRE_PATH
```

## Outputs

- Canonically compiled EPUB is written atomically to `books/<book-slug>/exports/<book-slug>.epub`.
- Derivative formats are written to the same directory as `books/<book-slug>/exports/<book-slug>.<format>`.
- Export results are logged to `books/<book-slug>/reports/results/export-book.yaml`.

## Runtime Notes

- The export command refuses to run without a valid `qa-approved` checkpoint. If it blocks, run the active harness check-translation skill first.
- Use bounded file-reading to inspect `reports/results/export-book.yaml` for the per-format success status and any EPUBCheck warnings.
- Do not attempt to validate or modify the resulting `.epub` files by hand - trust the EPUBCheck pipeline.
