# Phase 5: QA Review Gate - Context

**Gathered:** 2026-06-01
**Status:** Ready for planning

<domain>
## Phase Boundary

Produce deterministic, non-mutating quality reports across all translated chapters and require explicit user approval (via a `qa-approved` checkpoint) before allowing any ebook or format conversions.

* **In Scope:**
  - Create the CLI validation engine (`$check-translation` skill and helper scripts).
  - Read-only checks that do not modify raw or translated content in any way.
  - Structural checks: identify missing, empty, out-of-order, or incomplete chapters (unbalanced quotes, missing ending punctuation).
  - Residue checks: detect Chinese characters (CJK Unified Ideographs `\u4e00-\u9fff`) and Chinese punctuation (e.g. `。，、「」`).
  - Length checks: flag abnormal character lengths using raw Chinese vs. translated Vietnamese character ratios (< 0.6 or > 2.0).
  - Conflict checks: flag unresolved terms from `reports/glossary-conflicts.yaml`.
  - Checkpoint creation: generate `checkpoints/qa-approved.yaml` with evidence hashes of all translated files.
* **Out of Scope:**
  - Automatic modifications or corrections of translation text.
  - Calibre format conversion or EPUB assembly (Phase 6).
  - Context-dependent or semantic LLM quality audits (deferred to v2).

</domain>

<decisions>
## Implementation Decisions

### D-01: Non-Mutating Verification Engine
- All QA checks are strictly read-only.
- The verification scripts will scan the `chapters.yaml` catalog, `state.yaml`, raw chapter files under `raw/`, translation files under `translations/`, and `reports/glossary-conflicts.yaml`.
- Absolutely no file writes or edits are performed on raw or translation contents, preserving the integrity of literary work.

### D-02: Structural Integrity Checks
- **Missing & Empty:** Every chapter listed in `chapters.yaml` must have a corresponding file under `translations/` that exists, is non-empty, and has `COMPLETED` status in `state.yaml`.
- **Out-of-Order:** Verify that all translated chapters are sequentially present without gaps from `chapter_id=1` to the latest completed chapter.
- **Incompleteness Heuristics:**
  - **Unbalanced Quotes:** Scan text to identify mismatched quote pairs (e.g., standard double quotes `"` vs `"` or specialized CJK quotation marks `「` vs `」` if used in style guides).
  - **Missing Terminal Punctuation:** Ensure each chapter ends with valid punctuation (`.`, `!`, `?`, `”`, `」`, `...`).

### D-03: Suspicious Chinese Residue Check
- The scanner flags any CJK Unified Ideographs (`\u4e00-\u9fff`) and common Chinese symbols & punctuation (such as `。`, `，`, `、`, `「`, `」`, `『`, `』`) in the Vietnamese translations.
- Reports the exact line number, column index, and a 40-character context snippet (20 characters before, 20 characters after) for ease of manual review.

### D-04: Abnormal Chapter Length Heuristics
- Heuristic comparison is based on the ratio of translated Vietnamese characters to original Chinese characters:
  - **Vietnamese Character Count / Chinese Character Count**
  - Flags chapters where **Ratio < 0.6** (suspiciously short, indicating possible truncated paragraphs or skipped sections).
  - Flags chapters where **Ratio > 2.0** (suspiciously long, indicating possible translation loop repeats or prompt leak residue).
- These ratio bounds are defined as configurable default settings, allowing style or project customization if needed.

### D-05: Unresolved Glossary Conflicts
- Directly reads the active `reports/glossary-conflicts.yaml` produced during translation progressive merges.
- Any conflict records present in this file are flagged as unresolved.
- Resolution consists of the user editing `glossary.yaml` manually and/or clearing/resolving the conflict log file.

### D-06: QA Report & Gate Approval
- **QA Report Output:** Written atomically to `reports/qa-report.yaml` containing the summary statistics and detailed finding arrays.
- **Console Display:** The `$check-translation` skill or CLI command renders a clean Markdown table summarizing passed/failed checks.
- **Checkpoint Gating:** Implementing `main.py approve-qa --workspace <path>` which creates `checkpoints/qa-approved.yaml` with the evidence hashes of the translated files.
- The `qa-approved` checkpoint is validated in downstream Phase 6 scripts before exporting.

</decisions>

<canonical_refs>
## Canonical References

- `.planning/PROJECT.md` - Overall system constraints and stack definitions.
- `.planning/REQUIREMENTS.md` - Quality Assurance requirements `QUAL-01` through `QUAL-05`.
- `.planning/ROADMAP.md` - Roadmap details for Phase 5.
- `src/dich_truyen_agent/checkpoints.py` - Standard checkpoint and gate logic.
- `src/dich_truyen_agent/models.py` - Core models and validation schemas.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `check_gate()` and `approve_checkpoint()` in `src/dich_truyen_agent/checkpoints.py` for gated checkpoints.
- `workspace_paths()` in `src/dich_truyen_agent/paths.py` for canonical workspace paths.
- `load_yaml_model()` and `atomic_write_yaml()` in `src/dich_truyen_agent/storage.py` for file operations.

### Integration Points
- Update `src/dich_truyen_agent/cli.py` to support `check-translation` and `approve-qa` subcommands.
- Add `src/dich_truyen_agent/qa.py` (or similar) containing the core QA validation functions.

</code_context>

<specifics>
## Specific Ideas

- **Detailed Finding Snippets:** Keep snippet matching robust to avoid false positives on standard ASCII symbols or Vietnamese diacritics.
- **Visual Terminal Output:** Render clean CLI summaries with color-coded markers (e.g. green for passed, red/yellow for findings) to make local user review highly interactive.

</specifics>

<deferred>
## Deferred Ideas

- Target re-translation of specific chapters (deferred to v2 / TRAN-08).
- Semantic translation auditing using LLM evaluation agents (deferred to v2 / QUAL-06).

</deferred>

---

*Phase: 5-qa-review-gate*
*Context gathered: 2026-06-01*
