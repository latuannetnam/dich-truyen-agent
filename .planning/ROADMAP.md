# Roadmap: Dich Truyen Agent

## Overview

Dich Truyen Agent is built as a layered, dependency-driven local workflow. The roadmap first
establishes filesystem contracts and safe state transitions, then adds trustworthy batch
crawling, glossary lifecycle, sequential native-agent translation, deterministic QA, and
validated ebook export. Each phase leaves an inspectable capability that later phases consume.

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

- [x] **Phase 1: Workspace Contracts and Skill Skeletons** - Establish the safe local foundation (completed 2026-05-31)
      shared by every workflow step.

- [x] **Phase 2: Crawl and Raw Review Gate** - Crawl books autonomously into validated raw
      workspaces and require user approval.

- [ ] **Phase 3: Glossary Lifecycle** - Generate, evolve, and manually maintain safe terminology
      mappings.

- [ ] **Phase 4: Sequential Agent-Native Translation** - Translate chapters through isolated
      workers with strict continuity and safe resume behavior.

- [ ] **Phase 5: QA Review Gate** - Generate deterministic quality findings and require user
      approval before export.

- [ ] **Phase 6: EPUB 3.3 and Format Conversion** - Produce validated canonical EPUB ebooks and
      Calibre derivatives through the complete skill surface.

## Phase Details

### Phase 1: Workspace Contracts and Skill Skeletons

**Goal**: Establish stable schemas, atomic state changes, approval gates, style files, and
project-local skill entrypoint contracts.
**Depends on**: Nothing (first phase)
**Requirements**: [WORK-01, WORK-02, WORK-03, WORK-04, STYL-01, STYL-02]
**Success Criteria** (what must be TRUE):

  1. User can initialize a new book workspace and inspect documented metadata, chapter catalog,
     chapter state, staging, report, checkpoint, and output locations.

  2. Interrupted helper writes do not replace valid files, and resume preserves completed work.
  3. A gated helper rejects execution until its required checkpoint exists.
  4. User can start with `tien_hiep.yaml` or select a custom YAML style without changing code.

**Plans**: 2 plans
Plans:

- [x] 01-01-PLAN.md: Define package layout, Pydantic contracts, workspace initialization, and atomic file
      operations.

- [x] 01-02-PLAN.md: Add checkpoint enforcement, style loading, default `tien_hiep` template, and skill
      skeleton contracts.

### Phase 2: Crawl and Raw Review Gate

**Goal**: Download a complete new book with autonomous batch execution, profile repair support,
compact reporting, and an explicit raw-content approval gate.
**Depends on**: Phase 1
**Requirements**: [CRAW-01, CRAW-02, CRAW-03, CRAW-04, CRAW-05, CRAW-06, CRAW-07, CRAW-08, CRAW-09, CRAW-10, CRAW-11]
**Success Criteria** (what must be TRUE):

  1. User can crawl a static book with HTTP and a JavaScript-rendered fixture through Playwright
     fallback.

  2. A batch crawl retries recoverable errors, resumes saved progress, and returns one compact
     result instead of streaming chapter content through the agent context.

  3. User can reuse a domain profile, keep a book-local override, and apply an agent-proposed
     local repair after failed extraction validation.

  4. CAPTCHA, login, and unrecoverable extraction cases stop safely with actionable guidance.
  5. User can inspect the crawl report and approve raw content before downstream work begins.

**Plans**: 3 plans

Plans:

**Wave 1**

- [ ] 02-01: Implement profile schema, HTTP extraction, encoding handling, and representative
      crawl fixtures.

**Wave 2** *(blocked on Wave 1 completion)*

- [ ] 02-02: Add resumable batch crawl, retries, Playwright fallback, compact results, and
      intervention detection.

**Wave 3** *(blocked on Wave 2 completion)*

- [ ] 02-03: Add crawl validation report, book-local profile repair flow, `$crawl-book`, and raw
      approval checkpoint.

### Phase 3: Glossary Lifecycle

**Goal**: Create a reviewable initial glossary and evolve it safely as translation progresses.
**Depends on**: Phase 2
**Requirements**: [GLOS-01, GLOS-02, GLOS-03, GLOS-04]
**Success Criteria** (what must be TRUE):

  1. User receives an initial glossary after approving crawled raw chapters.
  2. A chapter-level proposal can be merged without silently replacing canonical mappings.
  3. Duplicate terms and conflicting mappings are represented deterministically in a report.
  4. User can manually edit the documented glossary file and resume safely.

**Plans**: 2 plans

Plans:

- [ ] 03-01: Generate initial glossary proposals and define reviewable glossary storage.
- [ ] 03-02: Implement validated progressive merge, conflict reporting, snapshots, and manual
      edit workflow.

### Phase 4: Sequential Agent-Native Translation

**Goal**: Translate approved raw chapters in order through context-isolated workers while
keeping the orchestrator compact and recovery deterministic.
**Depends on**: Phase 3
**Requirements**: [TRAN-01, TRAN-02, TRAN-03, TRAN-04, TRAN-05, TRAN-06, TRAN-07]
**Success Criteria** (what must be TRUE):

  1. Translation refuses to start before raw-content approval exists.
  2. Each worker receives file paths for exactly one raw chapter, prior Vietnamese context,
     style, and glossary, then returns staged output with compact metadata.

  3. Only validated staged translations are promoted atomically, and glossary proposals flow
     through the safe merge contract.

  4. Chapters are translated strictly in order with configurable retry and backoff.
  5. Exhausted retries stop the run, and user can resume from the failed chapter without
     reprocessing completed chapters.
**Plans**: 3 plans

Plans:

- [ ] 04-01: Define and verify native Codex worker protocol, staging validation, and atomic
      promotion.

- [ ] 04-02: Implement sequential orchestration, previous-chapter context, retry-stop-resume,
      and glossary proposal handoff.

- [ ] 04-03: Add `$translate-book` end-to-end workflow and recovery-focused fixtures.

### Phase 5: QA Review Gate

**Goal**: Produce deterministic, non-mutating translation quality reports and require explicit
approval before export.
**Depends on**: Phase 4
**Requirements**: [QUAL-01, QUAL-02, QUAL-03, QUAL-04, QUAL-05]
**Success Criteria** (what must be TRUE):

  1. User can run QA across translated chapters without modifying translation files.
  2. Report identifies missing, empty, out-of-order, incomplete, and abnormal-length chapters.
  3. Report identifies suspicious Chinese residue and unresolved glossary conflicts.
  4. User can inspect the report and approve a QA checkpoint that enables export.

**Plans**: 2 plans

Plans:

- [ ] 05-01: Implement deterministic structural, residue, length, and glossary conflict checks.
- [ ] 05-02: Add QA report rendering, `$check-translation`, and QA approval checkpoint.

### Phase 6: EPUB 3.3 and Format Conversion

**Goal**: Export approved translations as a conformant canonical EPUB 3.3 ebook and derive other
formats through Calibre.
**Depends on**: Phase 5
**Requirements**: [SKIL-01, EXPT-01, EXPT-02, EXPT-03, EXPT-04, EXPT-05]
**Success Criteria** (what must be TRUE):

  1. Export refuses to run before QA approval exists.
  2. User can generate an EPUB 3.3 ebook with required navigation, metadata, and valid ZIP
     structure.

  3. EPUBCheck is mandatory: unavailable tooling and validation errors stop export with
     actionable guidance.

  4. User can generate AZW3, MOBI, and PDF derivatives from the accepted EPUB with Calibre.
  5. User can operate the complete workflow through separate crawl, translate, quality-check,
     and export skills.
**Plans**: 3 plans

Plans:

- [ ] 06-01: Build EPUB 3.3 package assembly and deterministic ZIP/EPUB invariant validation.
- [ ] 06-02: Integrate mandatory EPUBCheck and Calibre `ebook-convert` derivatives.
- [ ] 06-03: Add `$export-book`, verify the four-skill command surface, and exercise the full
      staged workflow.

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5 -> 6

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Workspace Contracts and Skill Skeletons | 2/2 | Complete   | 2026-05-31 |
| 2. Crawl and Raw Review Gate | 0/3 | Not started | - |
| 3. Glossary Lifecycle | 0/2 | Not started | - |
| 4. Sequential Agent-Native Translation | 0/3 | Not started | - |
| 5. QA Review Gate | 0/2 | Not started | - |
| 6. EPUB 3.3 and Format Conversion | 0/3 | Not started | - |
