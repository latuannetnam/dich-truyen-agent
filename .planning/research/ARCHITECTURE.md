# Architecture Research

**Domain:** Antigravity-first agent-native Chinese-to-Vietnamese novel translation workflow
**Researched:** 2026-05-31
**Confidence:** HIGH

## Recommended Architecture

### System Overview

```text
User
  |
  v
Project-local Antigravity skills
  |-- $crawl-book
  |-- $translate-book
  |-- $check-translation
  `-- $export-book
  |
  v
Deterministic Python helper package
  |-- workspace contracts and atomic state updates
  |-- HTTP crawler and Playwright fallback
  |-- profile validation and report generation
  |-- glossary merge and QA checks
  `-- EPUB 3.3 assembly and Calibre conversion
  |
  +------------------------------+
  |                              |
  v                              v
Book workspace                Crawl profile library
  |-- immutable catalog          `-- reusable domain YAML
  |-- per-chapter state
  |-- raw and translated text
  |-- style and glossary
  |-- reports and checkpoints
  `-- output artifacts
  |
  v
Context-isolated translation worker
  |-- reads one raw chapter, previous translation, style, glossary
  |-- writes staged Vietnamese output and glossary proposals
  `-- returns compact validated result metadata
```

The key boundary is intentional: agents decide and translate; Python validates, persists,
promotes, and exports. The orchestrator must never update persisted state by regex or treat an
unvalidated worker file as complete.

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| Antigravity skills | Guide the user through one workflow step and invoke helpers | Project-local `SKILL.md` files with concise protocols |
| Workspace models | Define metadata, immutable chapter catalog, chapter state, checkpoints, and reports | Pydantic models serialized to JSON |
| State store | Persist resumable status atomically | One JSON state file per chapter plus atomic temp-file replacement |
| Fetcher | Retrieve HTML with retries, encoding detection, and transport selection | HTTPX first; Playwright Chromium fallback |
| Crawl profile engine | Apply reusable domain YAML and per-book override YAML | Beautiful Soup + lxml selectors with validation |
| Translation orchestrator | Process chapters strictly in order and manage retries | Skill-level loop calling one context-isolated worker at a time |
| Translation worker | Translate one chapter and propose glossary additions | Native coding-agent worker protocol; direct staged-file writes |
| Glossary helper | Initialize, validate, deduplicate, and merge glossary CSV | Deterministic Python helper |
| QA helper | Generate reviewable report without rewriting literary output | Deterministic Python scans |
| Export helper | Assemble canonical EPUB 3.3 and invoke optional conversions | `zipfile`, XHTML generation, EPUBCheck, Calibre |

## Recommended Project Structure

```text
.agent/
`-- skills/
    |-- crawl-book/SKILL.md
    |-- translate-book/SKILL.md
    |-- check-translation/SKILL.md
    `-- export-book/SKILL.md

src/
`-- dich_truyen_agent/
    |-- cli.py
    |-- models.py
    |-- workspace.py
    |-- atomic.py
    |-- crawl/
    |   |-- fetch.py
    |   |-- browser.py
    |   |-- profiles.py
    |   `-- validate.py
    |-- glossary/
    |   |-- models.py
    |   `-- merge.py
    |-- qa/
    |   `-- report.py
    `-- export/
        |-- epub.py
        `-- calibre.py

crawl_profiles/
`-- <domain>.yaml

styles/
`-- tien_hiep.yaml

books/
`-- <book-slug>/
    |-- book.json
    |-- chapters.json
    |-- crawl-profile.yaml
    |-- style.yaml
    |-- glossary.csv
    |-- raw/
    |   `-- 000001.txt
    |-- translated/
    |   `-- 000001.md
    |-- state/
    |   `-- 000001.json
    |-- staging/
    |-- reports/
    |   |-- crawl-report.md
    |   `-- qa-report.md
    |-- checkpoints/
    |   |-- crawl-approved.json
    |   `-- qa-approved.json
    `-- output/
        |-- book.epub
        |-- book.azw3
        |-- book.mobi
        `-- book.pdf
```

### Structure Rationale

- **Separate immutable catalog from mutable state:** `chapters.json` records the discovered
  chapter list after crawl approval; `state/<index>.json` records mutable processing state.
  This avoids rewriting a very large shared JSON document after every chapter.
- **Keep worker output staged:** translations are promoted only after helper validation passes.
- **Copy active profile and style into the book workspace:** later resume runs use the same
  inputs even if shared defaults change.
- **Store checkpoint markers:** translation and export skills can enforce the required user
  review gates without relying on chat history.

## Architectural Patterns

### Pattern 1: Skill as Orchestrator, Script as Authority

**What:** Skills define the conversational workflow and recovery path. Python helpers own
schema validation, state transitions, and artifact generation.

**When to use:** Every v1 workflow step.

**Trade-offs:** Skills remain readable and portable, while helpers are testable. The cost is
maintaining clear command contracts.

### Pattern 2: Validate Before Promote

**What:** A worker writes to `staging/`. A helper checks file presence, non-empty content,
formatting, remaining Chinese characters, and structured worker metadata before atomically
promoting output and advancing state.

**When to use:** Translation result handling and crawl-profile repair.

**Trade-offs:** Adds explicit promotion steps but prevents partial or malformed output from
being treated as complete.

### Pattern 3: Domain Profile Plus Book Override

**What:** Try `crawl_profiles/<domain>.yaml`, validate the result, then allow an agent-generated
book-local override if needed.

**When to use:** Every crawl.

**Trade-offs:** Shared profiles accelerate repeat domains; local overrides prevent one unusual
book from changing behavior for every book on that domain.

### Pattern 4: Sequential Worker Chain

**What:** Dispatch exactly one chapter worker, validate and promote output, merge glossary
proposals, then dispatch the next chapter with the prior translated chapter as context.

**When to use:** All v1 translation runs.

**Trade-offs:** Throughput is lower than adjacent concurrency, but continuity and recovery are
straightforward and align with the user's quality priority.

## Data Flow

### Crawl Flow

```text
$crawl-book URL
  -> initialize workspace
  -> try domain profile with HTTP fetcher
  -> validate chapter catalog and sampled content
  -> if render gap: retry with Playwright
  -> if profile gap: agent repairs book override
  -> validate again
  -> write raw files, immutable chapters.json, crawl-report.md
  -> user reviews raw data
  -> write checkpoints/crawl-approved.json
```

### Translation Flow

```text
$translate-book <book>
  -> require crawl-approved checkpoint
  -> snapshot style.yaml
  -> create initial glossary from raw samples
  -> for each unfinished chapter in order:
       dispatch one isolated worker
       worker reads raw + previous translation + style + glossary
       worker writes staging translation + proposals + result JSON
       helper validates staged artifacts
       helper atomically promotes output and advances state
       helper merges validated glossary proposals
       retry with backoff on failure; stop after configured limit
```

### QA and Export Flow

```text
$check-translation <book>
  -> scan promoted translations deterministically
  -> write reports/qa-report.md
  -> user reviews report
  -> write checkpoints/qa-approved.json

$export-book <book> [format]
  -> require qa-approved checkpoint
  -> assemble EPUB 3.3
  -> validate container invariants and run EPUBCheck if installed
  -> optionally run Calibre ebook-convert for AZW3/MOBI/PDF
```

## Scaling Considerations

This is a single-operator local workflow. The primary scaling dimension is chapter count, not
concurrent users.

| Scale | Architecture Adjustments |
|-------|--------------------------|
| 1-100 chapters | Straightforward file operations and full QA scan |
| 100-3,000 chapters | Per-chapter state files, sampled crawl validation, bounded glossary prompts |
| 3,000+ chapters | Incremental QA indexes, report pagination, and optional volume export |

### Scaling Priorities

1. **First bottleneck:** translation latency and context size. Keep one chapter per worker and
   pass paths rather than raw text through the orchestrator.
2. **Second bottleneck:** repeated full-workspace scans. Derive summaries incrementally from
   per-chapter state once real workloads justify it.

## Anti-Patterns

### Shared Mutable Mega-Manifest

**What people do:** Rewrite a large `book.json` after every worker action.

**Why it is wrong:** It amplifies corruption risk, makes recovery harder, and creates future
concurrency hazards.

**Do this instead:** Keep immutable chapter catalog data separate from small atomic chapter
state files.

### Trusting Agent Output Without Validation

**What people do:** Mark a chapter translated because a worker returned success.

**Why it is wrong:** The file may be empty, malformed, incomplete, or written to the wrong path.

**Do this instead:** Validate staged files and structured metadata before atomic promotion.

### Migrating Old EPUB Assembly Unchanged

**What people do:** Copy the old EPUB 2-style assembler.

**Why it is wrong:** EPUB 3.3 requires an XHTML navigation document and specific metadata such
as `dcterms:modified`; NCX alone is legacy.

**Do this instead:** Implement EPUB 3.3 output and run EPUBCheck.

## Integration Points

### External Services and Tools

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| Target novel websites | HTTPX requests, optional Chromium render | Respect delay and stop on CAPTCHA/login |
| Antigravity native worker capability | Skill-level dispatch with path-only protocol | Runtime adapter owns spawn syntax |
| EPUBCheck | Optional subprocess after assembly | Official conformance checker |
| Calibre `ebook-convert` | Subprocess from canonical EPUB | Required only for AZW3/MOBI/PDF |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| Skill -> helper | CLI arguments and JSON result | Stable and portable |
| Helper -> workspace | Validated JSON/YAML/CSV and atomic writes | Python is state authority |
| Skill -> translation worker | Absolute paths and structured result schema | Avoid raw-text leakage into orchestrator |
| Worker -> helper | Staged files and compact JSON | Never mutate promoted state directly |

## Sources

- `.planning/PROJECT.md` - approved product boundaries
- `D:\latuan\Programming\dich-truyen-tien-hiep\docs\ARCHITECTURE.md` - old pipeline reference
- `D:\latuan\Programming\dich-truyen-tien-hiep\.agents\skills\translate-error-chapters\SKILL.md` - prior worker isolation experiment
- https://www.w3.org/TR/epub-33/ - EPUB 3.3 packaging, navigation, and metadata requirements
- https://github.com/w3c/epubcheck - official EPUB conformance checker
- https://playwright.dev/python/docs/intro - Playwright as general-purpose browser automation

---
*Architecture research for: Antigravity-first agent-native novel translation workflow*
*Researched: 2026-05-31*
