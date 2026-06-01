---
name: "export-book"
description: "Export an approved translation workspace as ebook artifacts"
metadata:
  short-description: "Export an approved translation workspace as ebook artifacts"
---

# Export Book

Arguments: `books/<book-slug>/` and requested output formats.

Run the deterministic `check-gate` helper for the incoming `qa-approved` checkpoint before
reading translations. Write exports beneath `books/<book-slug>/exports/` and compact helper
metadata beneath `books/<book-slug>/reports/results/`.

Failure: ebook export is not implemented by Phase 1. Stop and report that Phase 6 owns this step.
