---
name: "check-translation"
description: "Check translated chapters and prepare QA review metadata"
metadata:
  short-description: "Check translated chapters and prepare QA review metadata"
---

# Check Translation

Arguments: `books/<book-slug>/`.

Read translations from `books/<book-slug>/translations/` and write compact helper metadata
beneath `books/<book-slug>/reports/results/`. A future QA workflow will produce the
`qa-approved` checkpoint after review.

Failure: translation QA is not implemented by Phase 1. Stop and report that Phase 5 owns this
step.
