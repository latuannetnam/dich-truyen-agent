---
phase: epub-and-format-conversion
plan: "02"
subsystem: process-wrappers
tags: [epubcheck, calibre, subprocess, exit-codes, warning-handling]
requires: [06-02-PLAN.md]
provides:
  - Subprocess wrappers for EPUBCheck in src/dich_truyen_agent/export.py with automatic PATH and env variables discovery
  - Calibre ebook-convert subprocess wrappers in src/dich_truyen_agent/export.py supporting azw3, mobi, and pdf formats
  - Graceful third-party missing tool error handling and actionable instructions
affects: [export, external-tools]
tech-stack:
  added: []
  patterns: [subprocess-wrapper-execution, system-path-discovery, graceful-error-fallbacks, optional-derivative-warnings]
key-files:
  created: []
  modified:
    - src/dich_truyen_agent/export.py
requirements-completed: [EXPT-04, EXPT-05]
duration: 15 min
completed: 2026-06-01
---

# Phase 06 Plan 02: EPUBCheck and Calibre Subprocess Wrappers Summary

**Implemented sandbox-safe subprocess executables discovery and runners for EPUBCheck and Calibre converters with robust error-handling logic.**

## Accomplishments

- Built the EPUBCheck runner `run_epubcheck` in `src/dich_truyen_agent/export.py`:
  - Detects `epubcheck` command in PATH or via `DICH_TRUYEN_EPUBCHECK_PATH` environment variable (handling both binaries and Java JAR scripts).
  - Performs validation checks on temporary packages before canonical promotion.
  - Aborts compilation and prints detailed errors when EPUBCheck reports issues or if EPUBCheck/Java is completely missing.
- Programmed the Calibre converter `run_calibre_convert` in `src/dich_truyen_agent/export.py`:
  - Looks up Calibre `ebook-convert` utility in system PATH or Windows standard installation folders (e.g. `C:\Program Files\Calibre2\`).
  - Calls conversion subprocesses to export `AZW3`, `MOBI`, and `PDF` derivatives in a sandbox-safe manner.
  - Skips derivative conversions with a clear warning if Calibre is missing without interrupting EPUB packaging.

## Verification

- `uv run pytest tests/test_export.py -q` - passed successfully
- `uv run pytest -q` - passed successfully
- `uv run ruff check src tests` - passed successfully
