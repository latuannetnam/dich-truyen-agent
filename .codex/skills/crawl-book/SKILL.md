---
name: "crawl-book"
description: "Crawl a novel into a validated local workspace"
metadata:
  short-description: "Crawl a novel into a validated local workspace"
---

# Crawl Book

Arguments: book URL, `books/<book-slug>/`, and optional crawl profile.

The workspace boundary is `books/<book-slug>/raw/`. Deterministic helpers must write compact
metadata beneath `books/<book-slug>/reports/results/`; do not return chapter bodies or verbose
logs through agent context.

Incoming checkpoint: none. A future crawl workflow will produce the `crawl-approved`
checkpoint after review.

Failure: crawling is not implemented by Phase 1. Stop and report that Phase 2 owns this step.
