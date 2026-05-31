# Phase 1: Workspace Contracts and Skill Skeletons - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md - this log preserves the alternatives considered.

**Date:** 2026-05-31
**Phase:** 1-workspace-contracts-and-skill-skeletons
**Areas discussed:** Book workspace layout, initialization and resume rules, approval checkpoint
records, style and skill contracts

---

## Book Workspace Layout

| Decision | Selected | Alternatives considered |
|----------|----------|-------------------------|
| Default workspace root | `books/<book-slug>/` | `workspace/<book-slug>/`; user-supplied path only; the agent decides |
| Top-level layout | Stage-oriented folders | Chapter-oriented folders; hybrid layout; the agent decides |
| Catalog and state storage | Separate YAML files | Separate JSON files; combined YAML manifest; the agent decides |
| Chapter filenames | Stable numeric IDs with readable slugs | Numeric IDs only; original titles only; the agent decides |

**User's choice:** Use inspectable stage-oriented book workspaces with separate immutable and
mutable YAML files.
**Notes:** Chapter filenames should remain ordered while still being readable during manual
inspection.

---

## Initialization and Resume Rules

| Decision | Selected | Alternatives considered |
|----------|----------|-------------------------|
| Existing target directory | Refuse unless explicitly resumed | Resume automatically; prompt to overwrite or resume; the agent decides |
| Completed files during resume | Validate and preserve | Trust state without validation; reprocess completed work; the agent decides |
| Orphan temporary files | Ignore and report | Delete automatically; attempt recovery; the agent decides |
| Invalid completed canonical file | Stop with actionable error | Mark pending automatically; restore from staging; the agent decides |

**User's choice:** Resume is explicit, validates completed files, and fails closed on
inconsistencies.
**Notes:** Preserve the last valid canonical file and keep interrupted-write evidence available
for diagnosis.

---

## Approval Checkpoint Records

| Decision | Selected | Alternatives considered |
|----------|----------|-------------------------|
| Checkpoint representation | Structured YAML with evidence hashes | Simple marker; YAML without hashes; the agent decides |
| Reviewed inputs changed | Invalidate checkpoint and stop | Warn and continue; keep approval for minor changes; the agent decides |
| Gate failure result | Compact actionable result with paths | Exception only; verbose dump; the agent decides |
| Checkpoint creation | Explicit approval helper command | Automatic after report generation; manual YAML editing; the agent decides |

**User's choice:** Approval records prove what was reviewed and require deliberate user action.
**Notes:** A stale approval must block downstream work rather than degrade into a warning.

---

## Style and Skill Contracts

| Decision | Selected | Alternatives considered |
|----------|----------|-------------------------|
| Book style selection | Copy selected YAML into workspace | Reference external path; embed fields in metadata; the agent decides |
| Bundled default style | `templates/styles/tien_hiep.yaml` | Python constant; dynamic generation; the agent decides |
| Phase-1 skill skeleton depth | Thin documented entrypoints | Empty placeholders; partial later workflow logic; the agent decides |
| Helper result surface | Compact validated files plus concise summary | Terminal only; verbose logs returned to skill; the agent decides |

**User's choice:** Snapshot the active style per workspace and keep skill/helper contracts thin,
stable, and context-efficient.
**Notes:** Later phases implement workflow behavior behind these boundaries.

---

## the agent's Discretion

None.

## Deferred Ideas

None.
