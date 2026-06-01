# Phase 5: QA Review Gate - Research

**Researched:** 2026-06-01
**Domain:** Deterministic translation quality checker, Chinese residue regex, relative character length ratios, glossary conflict reports, and QA checkpoint gates.
**Confidence:** HIGH

## Summary

Phase 5 introduces the deterministic, non-mutating Quality Assurance review gate for the Dich Truyen Agent workflow. It requires verifying all translated chapters for structural gaps (missing, empty, or out-of-order files), incompleteness (unbalanced quotes, missing ending punctuation), Chinese residue (CJK ideographs and punctuation), abnormal lengths (Vietnamese-to-Chinese character ratio), and unresolved glossary conflicts without modifying any translation files. Finally, the user can inspect the generated QA report and approve a gated `qa-approved` checkpoint to unlock ebook export.

---

## Recommended Architecture

### 1. Domain Models (`src/dich_truyen_agent/models.py`)

To support structured QA verification reporting, we will add the following Pydantic models:

* `QAFindingType` (Enum): `structural`, `residue`, `length`, `glossary`
* `QAFinding` (BaseModel):
  - `chapter_id`: `int`
  - `finding_type`: `QAFindingType`
  - `severity`: `str` (`warning` or `error`)
  - `message`: `str`
  - `details`: `dict` (e.g. line, column, snippet, ratio, or conflict details)
* `QAReport` (BaseModel):
  - `schema_version`: `int = 1`
  - `generated_at`: `datetime`
  - `summary`: `dict` containing total chapters, passed checks, error counts, warning counts.
  - `findings`: `list[QAFinding]`

### 2. QA Check Engine (`src/dich_truyen_agent/qa.py`)

A new module implementing read-only verification functions:
* **Function:** `run_qa_check(workspace_root: Path) -> QAReport`
* **Checks:**
  1. **Structural Checks (QUAL-02):**
     - Scans `chapters.yaml` and `state.yaml`.
     - Flags any chapter listed in the catalog that is missing in `translations/` or has a state other than `COMPLETED` as `error`.
     - Flags any file under `translations/` that is empty or contains only whitespace as `error`.
     - Verifies contiguous sequence of `chapter_id` starting from 1 to check for out-of-order gaps.
  2. **Incompleteness Heuristics (QUAL-02):**
     - Checks for unbalanced double quotes (`"` vs `"`), specialized CJK brackets if configured (e.g. `「` vs `」`, `『` vs `』`), and standard parentheses.
     - Checks for missing terminal punctuation: Ensures the final character (excluding trailing quotes or whitespace) is `.`, `!`, `?`, `”`, `」`, or `...`.
  3. **Chinese Residue Scan (QUAL-03):**
     - Checks for CJK Unified Ideographs (`\u4e00-\u9fff`) and CJK symbols and punctuation (`\u3000-\u303f`: `。`, `，`, `、`, `「`, `」`, `『`, `』`).
     - Extracts the line number, column, matching characters, and a context snippet (20 chars before, 20 chars after).
  4. **Abnormal Length Check (QUAL-03):**
     - Loads raw Chinese chapter file length and translated Vietnamese file length.
     - Ratio = (Vietnamese character count) / (Chinese character count).
     - Flags as `warning` if **Ratio < 0.6** or **Ratio > 2.0**.
  5. **Glossary Conflict Scan (QUAL-03):**
     - Loads `reports/glossary-conflicts.yaml`.
     - Flags any conflict logged in this file as `warning` / `error`.

### 3. CLI Integration (`src/dich_truyen_agent/cli.py`)

* **Command:** `main.py check-translation --workspace <path>`
  - Executes `run_qa_check()`.
  - Atomically writes the model to `reports/qa-report.yaml`.
  - Renders a beautiful terminal summary table (green for pass, yellow/red for warnings/errors).
* **Command:** `main.py approve-qa --workspace <path>`
  - Enforces that QA has run and reports no blocking errors.
  - Calls `approve_checkpoint(workspace, CheckpointType.QA_APPROVED, "reports/qa-report.yaml", [translation files...])` to produce `checkpoints/qa-approved.yaml`.

---

## Validation Architecture

We will implement isolated unit and integration tests under `tests/test_qa.py` to verify:

| Requirement | Automated Coverage |
|-------------|--------------------|
| **QUAL-01 / QUAL-04** | Verify QA runs successfully in read-only mode and does not alter any raw or translation files. |
| **QUAL-02** | Test structural diagnostics by verifying that missing, empty, out-of-order, or truncated translations are caught. |
| **QUAL-03** | Verify that CJK residue (both ideographs and symbols) is detected, abnormal lengths are flagged, and glossary conflicts are listed. |
| **QUAL-05** | Verify that `approve-qa` successfully generates the `qa-approved.yaml` checkpoint containing evidence hashes of all translations. |

---

## Security & STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-05-01 | Tampering | Checkpoint verification | Mitigate | Gated export requires a validated, un-tampered `qa-approved.yaml` checkpoint whose evidence hashes match current files exactly. |
| T-05-02 | Denial of Service | Chinese residue regex | Mitigate | Keep the CJK detection regex simple and fast to avoid CPU exhaustion on very large text files. |

---

*Phase: 05-qa-review-gate*
*Research complete: 2026-06-01*
