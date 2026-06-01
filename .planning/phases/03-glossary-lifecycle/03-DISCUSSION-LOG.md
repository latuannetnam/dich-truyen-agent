# Phase 3: Glossary Lifecycle - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-01
**Phase:** 3-Glossary Lifecycle
**Areas discussed:** Glossary Storage Format and Schema, Initial Glossary Generation Strategy, Progressive Merging and Conflict Handling, Manual Edits and Snapshotting

---

## Glossary Storage Format and Schema

| Option | Description | Selected |
|--------|-------------|----------|
| Option A | Flat Key-Value Schema (Simple mapping in YAML) | |
| Option B | Structured Term Schema (Rich metadata with translation, category, source, is_canonical, note) | ✓ |

**User's choice:** Option B: Structured Term Schema.
**Notes:** Helps track locks, category filters, and audit source metadata to assist sequential subagents in downstream translation.

---

## Initial Glossary Generation Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Option A | Deterministic NLP Segmenter + Single-Pass LLM/Agent translation of top frequency terms | |
| Option B | Pure LLM/Agent scan and extraction of sample chapters (e.g., first few chapters) | ✓ |

**User's choice:** Option B: Pure LLM/Agent scan of sample chapters.
**Notes:** Better context awareness and extraction accuracy for names, sects, and proper terms inside their actual literary exposition.

---

## Progressive Merging and Conflict Handling

| Option | Description | Selected |
|--------|-------------|----------|
| Option A | Non-blocking Merge - Preserve existing terms (prioritize is_canonical), write conflicts to reports/glossary-conflicts.yaml, print warnings without stopping the run | ✓ |
| Option B | Blocking Merge - Stop translation immediately on any conflicting term proposal, requiring user resolution in glossary.yaml | |

**User's choice:** Option A: Non-blocking Merge.
**Notes:** Prioritizes `is_canonical: true` terms and provides a conflict report without breaking the pipeline.

---

## Manual Edits and Snapshotting

| Option | Description | Selected |
|--------|-------------|----------|
| Option A | Automatic backup snapshots (under books/<book-slug>/checkpoints/glossary-snapshots/) before merges, with is_canonical: true marking manual locks | ✓ |
| Option B | Simple direct edits to glossary.yaml, relying entirely on Git for tracking and versioning (no local backup snapshots) | |

**User's choice:** Option A: Automatic backup snapshots.
**Notes:** Provides local safety checkpoints before automated merges.

---

## the agent's Discretion

None - all major design options were discussed and approved.

## Deferred Ideas

None — discussion stayed within phase scope.
