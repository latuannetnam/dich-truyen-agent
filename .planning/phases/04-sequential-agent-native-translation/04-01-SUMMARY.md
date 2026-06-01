---
phase: sequential-agent-native-translation
plan: 01
subsystem: translation
tags: [prepare-context, promote-chapter, staging, fallback, validation]
requires: []
provides:
  - Context preparation helper resolving absolute paths and predecessor fallbacks
  - Staging contracts for translation texts and term proposals
  - Atomic promotion logic validating size, proposals, unlinking staging, and updating state.yaml
affects: [cli, workflow]
tech-stack:
  added: []
  patterns: [context-isolated-context-resolution, atomic-promotion-flow, path-traversal-protection]
key-files:
  created: []
  modified:
    - src/dich_truyen_agent/workspace.py
    - src/dich_truyen_agent/cli.py
    - tests/test_translation.py
key-decisions:
  - "Isolate context preparation and promotions to CLI subcommands rather than inlining them."
  - "Enforce strict size and non-emptiness validations on staged files before promoting."
requirements-completed: [TRAN-01, TRAN-02, TRAN-03, TRAN-04]
duration: 15 min
completed: 2026-06-01
---

# Phase 04 Plan 01: Translation Primitives Summary

**Implemented context preparation helpers, staging contracts, atomic promotion engines, and corresponding unit tests.**

## Accomplishments

- Implemented `prepare_translation_context()` to verify the `crawl-approved` gate, load the catalog, and resolve absolute paths for raw text, style, glossary, and Chapter `N-1` translation context.
- Integrated predecessor translation fallback, returning null for previous context if Chapter `N-1` does not exist.
- Implemented `promote_chapter_translation()` to validate staged outputs (existence, non-emptiness, minimum size, proposals YAML syntax).
- Programmed atomic file movement of translation drafts, progressive proposals merging, state tracking updates, and staging directory cleanup.
- Registered CLI subcommands `prepare-translation-context` and `promote-chapter`.
- Added automated unit and integration tests covering context building, fallback resolution, and atomic promotions.

## Verification

- `uv run pytest tests/test_translation.py -q -k "context or promotion or cli"` - passed
- `uv run ruff check src tests` - passed
