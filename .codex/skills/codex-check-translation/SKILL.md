---
name: codex-check-translation
description: "Use when running the check-translation phase of the Chinese-to-Vietnamese novel translation pipeline in the codex harness."
---

<!-- GENERATED from .harness/source by tools/sync_harness_adapters.py. Do not edit directly. -->

# Codex-Check Translation

Deterministic, non-mutating quality check pipeline evaluating structural consistency, CJK residue, character length ratios, and glossary mapping conflicts. Creating a cryptographically secure `qa-approved` checkpoint unlocks final ebook exports.

## Workflow

1. **Run Quality Check Scan**:
   Execute the deterministic validation engine to audit all translated chapters:
   ```powershell
   $env:PYTHONUTF8=1
   uv run python main.py check-translation --workspace books/<book-slug>
   ```
   - This scan is completely non-mutating and will **never** modify any raw or translated text files.
   - Outputs a detailed findings report to `reports/qa-report.yaml`.
   - Renders a clean Markdown summary table to stdout classifying issues by Category, Chapter, Severity, and details.

2. **Diagnose and Resolve Findings**:
   Inspect findings reported in the terminal or `reports/qa-report.yaml` using bounded file-reading:
   - **Structural Findings:** Fix any missing chapters, empty files, or state inconsistencies in `state.yaml`.
   - **Chinese Residue Warnings:** Highlighted CJK characters or Chinese punctuation marks remaining in Vietnamese text. Manually clean these lines in the translation files using the active harness editing capability.
   - **Abnormal Lengths:** Warnings for chapters where the character length ratio relative to raw Chinese is too low (< 0.6) or too high (> 2.0) - indicating truncated prose or repeat output loops.
   - **Glossary Conflicts:** Terms flagged in `reports/glossary-conflicts.yaml`. Manually edit `glossary.yaml` to lock mapping or clear conflict listings.

3. **Approve QA Checkpoint**:
   Once errors are resolved or warnings reviewed, lock and authorize the workspace for export:
   ```powershell
   $env:PYTHONUTF8=1
   uv run python main.py approve-qa --workspace books/<book-slug>
   ```
   - Blocks approval if there are outstanding critical `error` severity findings.
   - Evidence hashing records the checksums of the QA report and every single promoted translation file.
   - Produces the secure `checkpoints/qa-approved.yaml` checkpoint file enabling the downstream export workflows.

## Runtime Notes

- The QA scan is safe to run repeatedly - it never mutates files.
- When manually fixing residue or length issues, edit `books/<book-slug>/translations/chuong-NNNN.txt` directly with the active harness editing capability, then re-run the scan.
- Do NOT bulk-read every translation file into your main context. Trust the YAML report summaries.
