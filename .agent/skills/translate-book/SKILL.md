---
name: "translate-book"
description: "Translate an approved novel workspace sequentially"
metadata:
  short-description: "Translate an approved novel workspace sequentially"
---

# Translate Book

Arguments: `books/<book-slug>/` and optional resume controls.

Run the deterministic `check-gate` helper for the incoming `crawl-approved` checkpoint before
using `books/<book-slug>/raw/`. Keep compact helper metadata beneath
`books/<book-slug>/reports/results/`; do not inject chapter bodies or verbose logs into agent
context.

Failure: translation is not implemented by Phase 1. Stop and report that Phase 4 owns this step.
