# Requirements: Dich Truyen Agent

**Defined:** 2026-05-31
**Core Value:** Produce resumable, high-quality Vietnamese novel translations through explicit
review checkpoints while keeping each agent task small, inspectable, and recoverable.

## v1 Requirements

Requirements for the initial release. Each requirement maps to one roadmap phase.

### Skills and Workspace

- [ ] **SKIL-01**: User can run separate project-local Codex skills for crawl, translate,
      quality check, and export.
- [ ] **WORK-01**: User can initialize a clean filesystem workspace for a new book without
      requiring data from the old application.
- [ ] **WORK-02**: User can inspect metadata, immutable chapter catalog data, and mutable
      per-chapter state in documented files.
- [ ] **WORK-03**: User can safely resume each workflow step because helper writes are atomic and
      completed work is not silently overwritten.
- [ ] **WORK-04**: User cannot start a gated workflow step until its required approval checkpoint
      exists.

### Crawling

- [ ] **CRAW-01**: User can crawl static chapter pages from a book URL with the HTTP crawler.
- [ ] **CRAW-02**: User can crawl JavaScript-rendered chapter pages through a Playwright fallback
      when static extraction is insufficient.
- [ ] **CRAW-03**: User can reuse a validated YAML crawl profile for books on the same domain.
- [ ] **CRAW-04**: User can keep a book-local crawl profile override when one book requires rules
      that should not change the shared domain profile.
- [ ] **CRAW-05**: Agent can propose and apply a book-local profile repair after deterministic
      extraction validation fails.
- [ ] **CRAW-06**: User can start one batch crawl that continues without agent interaction until
      the book is complete or an unrecoverable condition requires intervention.
- [ ] **CRAW-07**: User can resume a failed crawl from saved progress; the helper retries
      recoverable failures with backoff and switches from HTTP to Playwright when appropriate.
- [ ] **CRAW-08**: Agent receives a compact crawl result with status, progress, failure details,
      and report paths instead of chapter bodies or verbose logs.
- [ ] **CRAW-09**: User can inspect a crawl report covering chapter counts, duplicates, titles,
      sampled body lengths, and suspicious residue before approving raw content.
- [ ] **CRAW-10**: User is told to intervene when CAPTCHA, authentication, or an unrecoverable
      extraction failure prevents the crawler from continuing safely.
- [ ] **CRAW-11**: User can approve crawled raw content by creating a crawl checkpoint before
      glossary generation or translation begins.

### Styles and Glossary

- [ ] **STYL-01**: User can configure a book's translation behavior with a custom YAML style
      file.
- [ ] **STYL-02**: User can start from the bundled default `tien_hiep` YAML style template.
- [ ] **GLOS-01**: User receives an automatically generated initial glossary after approving
      crawled raw content.
- [ ] **GLOS-02**: Translation worker can propose new glossary terms after each translated
      chapter.
- [ ] **GLOS-03**: User receives a safely merged glossary after each chapter; duplicate proposals
      do not replace canonical mappings silently and conflicts are reported.
- [ ] **GLOS-04**: User can manually review and edit the documented glossary file before resuming
      translation.

### Translation

- [ ] **TRAN-01**: User cannot start translation until the crawl approval checkpoint exists.
- [ ] **TRAN-02**: User can translate a book through context-isolated workers that each process
      exactly one chapter.
- [ ] **TRAN-03**: Worker receives file paths for raw chapter text, active style, glossary, and
      the completed Vietnamese translation of the previous chapter instead of receiving the
      whole book through the orchestrator context.
- [ ] **TRAN-04**: User only receives promoted chapter translations after staged worker output
      passes deterministic validation and an atomic promotion step.
- [ ] **TRAN-05**: User receives chapters translated strictly in order so chapter `N` uses the
      completed Vietnamese output of chapter `N-1` as context.
- [ ] **TRAN-06**: User can configure retry count and backoff for chapter translation failures;
      the default retry limit is 3.
- [ ] **TRAN-07**: User sees translation stop after exhausted retries and can safely resume from
      the failed chapter after resolving the issue.

### Quality Assurance

- [ ] **QUAL-01**: User can run deterministic QA across all translated chapters.
- [ ] **QUAL-02**: User receives a QA report identifying missing, empty, out-of-order, or
      incomplete translated chapters.
- [ ] **QUAL-03**: User receives QA findings for suspicious Chinese residue, abnormal chapter
      lengths, and unresolved glossary conflicts.
- [ ] **QUAL-04**: User can review QA findings without the QA helper silently modifying
      translated content.
- [ ] **QUAL-05**: User can approve a QA checkpoint after reviewing the report, enabling export.

### Export

- [ ] **EXPT-01**: User cannot export a book until the QA approval checkpoint exists.
- [ ] **EXPT-02**: User can generate a canonical EPUB 3.3 ebook directly from approved
      translations.
- [ ] **EXPT-03**: User receives deterministic ZIP and EPUB structure validation before the
      canonical ebook is accepted.
- [ ] **EXPT-04**: User receives EPUBCheck validation; export stops with actionable guidance when
      EPUBCheck is unavailable or reports an error.
- [ ] **EXPT-05**: User can generate AZW3, MOBI, and PDF derivatives from the canonical EPUB
      through Calibre `ebook-convert`.

## v2 Requirements

Deferred to a future release. These are tracked but not included in the current roadmap.

### Translation and Quality

- **TRAN-08**: User can selectively retranslate chapters identified through QA review.
- **QUAL-06**: User can request an optional LLM second-review pass when deterministic QA is
  insufficient.

### Styles and Crawl Profiles

- **STYL-03**: User can select from additional bundled genre style templates.
- **CRAW-12**: User receives a broader curated library of reusable domain crawl profiles.

### Runtime Adapters

- **ADPT-01**: User can run equivalent workflows through an Antigravity adapter.
- **ADPT-02**: User can run equivalent workflows through a Claude Code adapter.

## Out of Scope

Explicitly excluded from v1 to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Legacy workspace migration | v1 optimizes a cleaner schema for new books |
| Web UI, REST API, or WebSocket monitoring | v1 is operated through Codex skills |
| Adjacent-chapter translation concurrency | strict sequential context is prioritized for translation quality |
| Automatic QA content corrections | literary changes require user review |
| CAPTCHA bypass, login automation, or advanced anti-bot evasion | crawler stops and requests user intervention |
| Direct LLM API orchestration as the primary runtime | v1 uses native coding-agent capability |

## Traceability

Updated during roadmap creation. Every v1 requirement must map to exactly one phase.

| Requirement | Phase | Status |
|-------------|-------|--------|
| SKIL-01 | Phase 6 | Pending |
| WORK-01 | Phase 1 | Pending |
| WORK-02 | Phase 1 | Pending |
| WORK-03 | Phase 1 | Pending |
| WORK-04 | Phase 1 | Pending |
| CRAW-01 | Phase 2 | Pending |
| CRAW-02 | Phase 2 | Pending |
| CRAW-03 | Phase 2 | Pending |
| CRAW-04 | Phase 2 | Pending |
| CRAW-05 | Phase 2 | Pending |
| CRAW-06 | Phase 2 | Pending |
| CRAW-07 | Phase 2 | Pending |
| CRAW-08 | Phase 2 | Pending |
| CRAW-09 | Phase 2 | Pending |
| CRAW-10 | Phase 2 | Pending |
| CRAW-11 | Phase 2 | Pending |
| STYL-01 | Phase 1 | Pending |
| STYL-02 | Phase 1 | Pending |
| GLOS-01 | Phase 3 | Pending |
| GLOS-02 | Phase 3 | Pending |
| GLOS-03 | Phase 3 | Pending |
| GLOS-04 | Phase 3 | Pending |
| TRAN-01 | Phase 4 | Pending |
| TRAN-02 | Phase 4 | Pending |
| TRAN-03 | Phase 4 | Pending |
| TRAN-04 | Phase 4 | Pending |
| TRAN-05 | Phase 4 | Pending |
| TRAN-06 | Phase 4 | Pending |
| TRAN-07 | Phase 4 | Pending |
| QUAL-01 | Phase 5 | Pending |
| QUAL-02 | Phase 5 | Pending |
| QUAL-03 | Phase 5 | Pending |
| QUAL-04 | Phase 5 | Pending |
| QUAL-05 | Phase 5 | Pending |
| EXPT-01 | Phase 6 | Pending |
| EXPT-02 | Phase 6 | Pending |
| EXPT-03 | Phase 6 | Pending |
| EXPT-04 | Phase 6 | Pending |
| EXPT-05 | Phase 6 | Pending |

**Coverage:**
- v1 requirements: 39 total
- Mapped to phases: 39
- Unmapped: 0

---
*Requirements defined: 2026-05-31*
*Last updated: 2026-05-31 after roadmap creation*
