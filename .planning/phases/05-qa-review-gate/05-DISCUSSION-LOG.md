# Phase 5: QA Review Gate - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-01
**Phase:** 5-QA Review Gate
**Areas discussed:** Suspicious Chinese Residue Check, Abnormal Chapter Length Heuristics, Unresolved Glossary Conflicts, Incomplete Chapter Detection Heuristics, QA Report Structure and Storage

---

## Suspicious Chinese Residue Check

| Option | Description | Selected |
|--------|-------------|----------|
| Option A | CJK Unified Ideographs (`\u4e00-\u9fff`) AND common CJK punctuation/symbols (e.g. `。，、「」`) | ✓ |
| Option B | CJK Unified Ideographs only, ignoring Chinese punctuation to prevent false positives | |
| Option C | Configurable regex pattern defined in the style/profile YAML | |

**User's choice:** Option A.
**Notes:** Provides a highly rigorous scan ensuring both actual characters and left-behind Chinese formatting/punctuation marks are flagged for cleaning.

---

## Abnormal Chapter Length Heuristics

| Option | Description | Selected |
|--------|-------------|----------|
| Option A | Relative comparison with raw Chinese character count (Vietnamese/Chinese character ratio < 0.6 or > 2.0) | ✓ |
| Option B | Absolute bounds (e.g., chapter text is less than 500 characters or greater than 10,000 characters) | |
| Option C | Statistical outlier detection based on the average translated length of all chapters in the book | |

**User's choice:** Option A.
**Notes:** Comparing relative text length ratio is extremely robust since chapters naturally vary in absolute length, and Vietnamese is consistently proportional to the Chinese source.

---

## Unresolved Glossary Conflicts

| Option | Description | Selected |
|--------|-------------|----------|
| Option A | Report any existing entries in `reports/glossary-conflicts.yaml` as unresolved conflicts. (Resolved by manually editing the glossary or clearing conflicts) | ✓ |
| Option B | Scan the translated text at runtime to find original Chinese terms and verify they match the glossary translation | |
| Option C | Both A and B (combining structural and runtime scanning checks) | |

**User's choice:** Option A.
**Notes:** Leverages the deterministic progressive merge logs created in Phase 3/4. Resolving conflicts is as simple as manual editing or clearing the conflict file, avoiding flaky runtime translation scanning.

---

## Incomplete Chapter Detection Heuristics

| Option | Description | Selected |
|--------|-------------|----------|
| Option A | Check for structural issues like empty/missing files, unbalanced quote pairs, and missing ending terminal punctuation (e.g. period/question/exclamation) | ✓ |
| Option B | Only check for empty/missing files, leaving literary completeness to manual review to avoid false positives | |
| Option C | Define customized textual markers (e.g., typical ending phrases like 'chua het', 'con tiep' etc.) | |

**User's choice:** Option A.
**Notes:** Balances automation and robustness by highlighting text structures that strongly correlate with cut-off translations or malformed quote sections.

---

## QA Report Structure and Storage

| Option | Description | Selected |
|--------|-------------|----------|
| Option A | Save as a structured YAML file at `reports/qa-report.yaml` and render it as a clean Markdown report/table in the terminal | ✓ |
| Option B | Save as a JSON file at `reports/qa-report.json` and print plain text output | |
| Option C | Write only to a Markdown file `reports/qa-report.md` | |

**User's choice:** Option A.
**Notes:** Perfect balance of clean developer-readable files (YAML) and beautiful console representation (Markdown/table) that fits into the command line interface seamlessly.

---

## Deferred Ideas

- Target re-translation of specific chapters (deferred to v2 / TRAN-08).
- Semantic translation auditing using LLM evaluation agents (deferred to v2 / QUAL-06).

---

*Phase: 5-qa-review-gate*
*Context gathered: 2026-06-01*
