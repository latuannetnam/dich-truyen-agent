# Dich Truyen Agent

## What This Is

Dich Truyen Agent is a Codex-first, agent-native workflow for crawling Chinese novels,
translating them into Vietnamese, checking translation quality, and exporting ebooks. It
rebuilds the useful behavior of the existing `D:\latuan\Programming\dich-truyen-tien-hiep`
application around coding-agent skills and small deterministic Python helpers instead of a
long-running application UI or API.

The primary user is the repository owner operating the workflow interactively through Codex.
The design keeps file contracts and helper scripts portable so adapters for Antigravity or
Claude Code can be added later.

## Core Value

Produce resumable, high-quality Vietnamese novel translations through explicit review
checkpoints while keeping each agent task small, inspectable, and recoverable.

## Requirements

### Validated

(None yet - ship to validate)

### Active

- [ ] Provide Codex skills for the separate crawl, translate, quality-check, and export steps.
- [ ] Crawl a new book from a URL using deterministic helpers, with agent-assisted extraction
      rule repair when a website is not handled correctly.
- [ ] Run crawl helpers as resumable batches until a book is complete or intervention is
      required, returning compact status metadata and report paths instead of chapter bodies.
- [ ] Persist new-book metadata, chapter status, raw text, translations, glossary, crawl rules,
      QA reports, and exports in a resumable filesystem workspace.
- [ ] Require a user checkpoint after crawl so raw chapter data can be reviewed before
      translation starts.
- [ ] Generate an initial glossary automatically from crawled chapters and merge validated new
      term proposals after each translated chapter.
- [ ] Translate chapters sequentially through context-isolated subagents so each chapter can use
      the completed Vietnamese translation of the previous chapter as context.
- [ ] Retry failed chapter translations with configurable backoff and stop the translation run
      if retries are exhausted so the user can resolve the issue and resume safely.
- [ ] Support custom YAML translation styles and ship a default `tien_hiep` template.
- [ ] Generate a deterministic QA report covering structural and glossary consistency issues,
      then require user review before export.
- [ ] Export a validated EPUB 3.3 ebook directly and convert it to AZW3, MOBI, or PDF through
      Calibre.

### Out of Scope

- Migrating or reading book workspaces created by the old application - v1 handles new books
  only and may use a cleaner schema.
- Web UI, REST API, and WebSocket monitoring - v1 is operated through Codex skills.
- First-class Antigravity or Claude Code adapters - contracts should remain portable, but Codex
  is the only supported runtime in v1.
- Parallel translation of adjacent chapters - v1 prioritizes continuity and quality through
  strict sequential translation.
- Automatic QA corrections or a second LLM review pass - v1 reports issues for user review.
- CAPTCHA bypass, login automation, or advanced anti-bot evasion - the crawler stops and reports
  these cases.

## Context

The previous application at `D:\latuan\Programming\dich-truyen-tien-hiep` is the functional
reference. It contains a Python CLI, FastAPI backend, Next.js frontend, tests, and real book
workspaces. Its useful behaviors include:

- LLM-assisted crawl pattern discovery, chapter downloads, resumable per-chapter status, and
  HTTP retry handling.
- Streaming crawl and translation, style templates, glossary generation, progressive glossary
  updates, TF-IDF glossary selection, dialogue-aware chunking, narrative context, and a polish
  pass.
- Direct EPUB assembly followed by Calibre conversion to AZW3, MOBI, or PDF.
- Operational scripts for metadata updates, chapter status reset, and translation consistency
  analysis.

The old repository also includes an experimental `translate-error-chapters` agent skill. Its
main-agent/subagent split is a useful starting point: the orchestrator handles paths and compact
metadata while a context-isolated worker reads a chapter, writes its translation, and returns a
small result. The new project generalizes that pattern into the primary workflow and removes
runtime-specific assumptions where practical.

The v1 user flow is deliberately checkpointed:

1. Crawl a new book from a URL.
2. Review the downloaded raw chapters.
3. Generate the initial glossary automatically and translate chapters sequentially.
4. Review the generated QA report.
5. Export EPUB and optionally convert it to another supported format.

## Constraints

- **Runtime**: Codex is the supported v1 agent runtime - file contracts and helpers must avoid
  unnecessary Codex-specific coupling so adapters can be added later.
- **Interface**: User-facing workflows are Codex skills - no UI or API server in v1.
- **Translation quality**: Chapters are translated strictly in order - chapter `N` uses the
  completed Vietnamese output of chapter `N-1` as context.
- **Failure handling**: Translation retries default to 3 attempts with backoff - exhausted
  retries stop the run rather than allowing lower-quality downstream translations.
- **Crawling**: Prefer HTTP for static HTML and use Playwright as a JavaScript-rendering
  fallback - CAPTCHA or authentication requirements stop the workflow for user action.
- **Token efficiency**: Crawl helpers run autonomously until completion or an unrecoverable
  condition - the agent receives compact result metadata and report paths, not raw chapter
  bodies or verbose logs.
- **Crawl rules**: Reuse validated domain profiles and allow per-book overrides - a failed
  validation must not silently produce incomplete raw data.
- **Styles**: Translation behavior is configured by YAML - ship `tien_hiep` as the default
  template and allow custom styles without code changes.
- **Export**: A validated EPUB 3.3 ebook is the canonical output - EPUBCheck is mandatory before
  AZW3, MOBI, and PDF Calibre conversions.
- **Compatibility**: Existing old-application book data is not a v1 input - optimize the new
  schema for the agent-native workflow.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Use a hybrid agent-native architecture | Agents are effective for analysis, translation, and repair; deterministic scripts are safer for metadata, validation, and export | - Pending |
| Operate v1 through Codex skills without UI or API | Keeps the first release focused on the agent-native workflow | - Pending |
| Support Codex first with portable contracts | Delivers one reliable runtime before adding adapters | - Pending |
| Use separate user checkpoints after crawl and QA | Raw extraction and translation quality should be reviewable before expensive or irreversible downstream steps | - Pending |
| Use HTTP crawl helpers with Playwright fallback | Static sites stay lightweight while JavaScript-rendered sites remain possible | - Pending |
| Run crawl helpers autonomously and report compact results | Avoid spending agent tokens on routine per-chapter progress while preserving logs for diagnosis | - Pending |
| Store reusable domain crawl profiles plus per-book overrides | Reuse known extraction rules without allowing one unusual book to affect every book on a domain | - Pending |
| Translate one chapter per isolated subagent, strictly sequentially | Previous translated output is needed for continuity, pronouns, and terminology | - Pending |
| Generate glossary automatically and merge new terms after each chapter | Later chapters immediately benefit from newly discovered names and terms | - Pending |
| Retry translation failures and then stop | Continuing after a missing chapter would weaken context for all later chapters | - Pending |
| Generate a QA report without automatic fixes | User review is safer for literary translation than silent content rewrites | - Pending |
| Generate validated EPUB 3.3 first and convert other formats with Calibre | Reuses a proven export flow while replacing the old EPUB 2-style output with a conformant canonical artifact | - Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition**:
1. Requirements invalidated? Move to Out of Scope with reason.
2. Requirements validated? Move to Validated with phase reference.
3. New requirements emerged? Add to Active.
4. Decisions to log? Add to Key Decisions.
5. Is "What This Is" still accurate? Update if drifted.

**After each milestone**:
1. Review all sections.
2. Confirm Core Value is still the right priority.
3. Audit Out of Scope and its reasons.
4. Update Context with the current implementation state and lessons learned.

---
*Last updated: 2026-05-31 after initialization*
