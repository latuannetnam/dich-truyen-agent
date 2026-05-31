# Phase 2: Crawl and Raw Review Gate - Context

**Gathered:** 2026-05-31
**Status:** Ready for planning

<domain>
## Phase Boundary

Download a new book into the Phase 1 filesystem workspace through deterministic HTTP-first
crawl helpers, reusable domain profiles, book-local repair overrides, resumable batch
execution, compact reports, and a user-approved raw-content checkpoint. This phase includes a
Playwright fallback for JavaScript-rendered content and safe intervention handling, but does
not include CAPTCHA bypass, authentication automation, glossary generation, translation, or
translation QA.

</domain>

<decisions>
## Implementation Decisions

### Crawl Configuration and Verification
- **D-01:** Add a configurable `max_chapters` crawl option. Its default is `0`, meaning
  unlimited.
- **D-02:** `max_chapters` limits chapter-body downloads only. Discovery still parses and
  validates the full catalog. Reports must clearly mark intentionally limited runs.
- **D-03:** Sleep after each successfully downloaded chapter. Use a configurable fixed delay
  with a default of `3` seconds; allow profile or command configuration to override it.
- **D-04:** Phase verification must perform a live crawl of exactly `10` chapters from
  `https://www.piaotia.com/html/8/8717/index.html`.

### Profile Ownership and Repair
- **D-05:** Reuse a validated shared YAML domain profile when one exists.
- **D-06:** If a shared domain profile fails extraction validation for a new book, stop and
  request agent-assisted repair. Preserve diagnostics; do not silently try generic selectors
  or switch transport as a substitute for rule repair.
- **D-07:** A repaired profile must be validated and presented for an explicit user choice:
  keep it as a book-local override or promote it to the shared domain profile. Keep it local
  unless promotion is explicitly approved.
- **D-08:** Reuse an existing validated book-local override automatically when resuming or
  recrawling that book, and report that the override is active.
- **D-09:** Offer shared-profile promotion immediately after a repaired book-local override
  passes validation.

### Catalog Completeness Rules
- **D-10:** Discover and validate the complete catalog before chapter-body downloads begin,
  including when `max_chapters` is nonzero.
- **D-11:** Duplicate chapter links or IDs are blocking catalog-validation errors. Stop before
  downloads and do not guess which entry is canonical.
- **D-12:** Clear numeric chapter gaps or repeats block downloads. Irregular titles or ordering
  that cannot be parsed reliably produce warnings for user judgment.
- **D-13:** Profiles define index pagination and chapter-list sections. Follow those rules
  deterministically and block when pages fail or sections overlap unexpectedly.

### Retries and Browser Fallback
- **D-14:** Use HTTP as the default transport. Switch to Playwright only when HTTP returns HTML
  but validation indicates missing rendered content, such as empty or clearly incomplete
  selector results consistent with JavaScript rendering.
- **D-15:** Retry recoverable HTTP failures, such as timeouts and `5xx` responses, up to `3`
  attempts on the same transport with configurable exponential backoff.
- **D-16:** Stop the batch at the first chapter that remains failed after retries. Persist the
  error and diagnostics, preserve completed chapters, and resume from the failed chapter after
  intervention. Do not crawl later chapters while a gap remains.
- **D-17:** CAPTCHA or authentication signals stop immediately without retries, bypass
  attempts, or login automation. Return actionable intervention metadata including the URL and
  diagnostic paths.

### Raw Review and Approval
- **D-18:** Generate a structured crawl report containing discovered and downloaded counts,
  crawl-limit status, active profile source, failures, duplicate and gap findings, per-chapter
  lengths, suspicious residue findings, and representative excerpts from the beginning,
  middle, and end of the crawled selection.
- **D-19:** Block raw approval for structural or extraction failures: missing files, empty
  bodies, catalog duplicates, clear numeric gaps, failed pages, or malformed state. Treat
  unusual lengths, uncertain ordering, and suspicious residue as warnings for user review.
- **D-20:** Allow explicitly partial approval for intentionally limited crawls. The report and
  checkpoint must record partial scope. Downstream full-book workflows must reject partial
  approval unless the selected crawl scope is complete.
- **D-21:** `$crawl-book` displays the report path and blocking or warning summary, asks for
  explicit user confirmation, and only then invokes the existing approval helper. Approval
  evidence hashes cover the reviewed report and crawled raw files.

### the agent's Discretion
No implementation decisions were delegated during discussion.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Scope and Requirements
- `.planning/PROJECT.md` - Defines the agent-native crawl workflow, compact helper-result
  constraint, HTTP-first strategy, profile reuse, and raw-review checkpoint.
- `.planning/REQUIREMENTS.md` - Defines Phase 2 requirements `CRAW-01` through `CRAW-11`.
- `.planning/ROADMAP.md` - Defines the fixed Phase 2 boundary, success criteria, and planned
  split across `02-01`, `02-02`, and `02-03`.

### Stack Guidance
- `.planning/research/STACK.md` - Defines `httpx`, Playwright fallback, Beautiful Soup, `lxml`,
  `chardet`, Pydantic validation, settings, and YAML handling guidance.

### Live Verification Target
- `https://www.piaotia.com/html/8/8717/index.html` - Required live verification URL. Crawl
  exactly `10` chapter bodies while still discovering and validating the full catalog.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/dich_truyen_agent/models.py`: Extend the existing strict Pydantic persisted models for
  crawl profiles, crawl reports, compact crawl results, and partial-approval scope metadata.
- `src/dich_truyen_agent/workspace.py`: Reuse workspace inspection, completed-artifact hash
  validation, and explicit resume behavior when promoting crawled raw files.
- `src/dich_truyen_agent/storage.py`: Reuse validated YAML loading, atomic file replacement, and
  SHA-256 helpers for profiles, reports, state, and raw artifacts.
- `src/dich_truyen_agent/checkpoints.py`: Reuse the explicit hash-backed approval flow. Extend
  the checkpoint contract so partial limited-crawl approvals cannot be mistaken for complete
  full-book approval.
- `src/dich_truyen_agent/cli.py`: Add deterministic crawl commands while preserving persisted
  compact `OperationResult` files beneath `reports/results/`.
- `.codex/skills/crawl-book/SKILL.md`: Replace the Phase 1 placeholder with the Phase 2
  orchestration flow and explicit review confirmation.

### Established Patterns
- Persisted file boundaries use Pydantic models with `extra="forbid"` and YAML serialization.
- Canonical files are written atomically. Resume validates completed artifacts and stops on
  conflicts rather than silently reprocessing them.
- Helpers print concise terminal summaries and persist compact result metadata instead of
  returning chapter bodies or verbose logs through agent context.
- Workspace paths remain relative, inspectable, and stage-oriented under `books/<book-slug>/`.

### Integration Points
- Populate `chapters.yaml`, `state.yaml`, and `raw/` through catalog discovery and sequential
  chapter-body downloads.
- Write crawl reports under `reports/` and compact command results under `reports/results/`.
- Create `checkpoints/crawl-approved.yaml` only after report review and explicit confirmation.
- Add reusable shared domain profiles plus workspace-local override storage without changing
  the Phase 1 workspace-resume guarantees.

</code_context>

<specifics>
## Specific Ideas

- The live acceptance exercise uses `https://www.piaotia.com/html/8/8717/index.html` with
  `max_chapters=10`.
- Crawl pacing is intentionally conservative: wait `3` seconds by default after every
  successfully downloaded chapter.
- Limited crawls are first-class testing runs, but their approval must remain visibly partial
  so later full-book workflows cannot accidentally consume incomplete raw data.

</specifics>

<deferred>
## Deferred Ideas

None - discussion stayed within phase scope.

</deferred>

---

*Phase: 2-crawl-and-raw-review-gate*
*Context gathered: 2026-05-31*
