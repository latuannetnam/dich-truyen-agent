# Project Research Summary

**Project:** Dich Truyen Agent
**Domain:** Codex-first agent-native Chinese-to-Vietnamese novel translation workflow
**Researched:** 2026-05-31
**Confidence:** HIGH

## Executive Summary

Dich Truyen Agent should be built as a skills-first local workflow, not as a migrated web
application and not as a direct LLM API client. Project-local Codex skills coordinate review
gates and native workers. A compact Python helper package remains authoritative for crawling,
schema validation, atomic state transitions, glossary merge, QA reporting, and export.

The old repository provides valuable proven behavior: HTTP crawling, selector discovery,
resumability, style YAML, glossary handling, direct EPUB creation, and Calibre conversion. It
also provides a useful experimental worker pattern. The new project should preserve those
lessons while adopting a cleaner book schema: immutable chapter catalog data, per-chapter state
files, staged worker output, explicit checkpoint markers, and validated domain profiles with
book-local overrides.

The main risks are silent crawl corruption, losing continuity through premature parallelism,
trusting worker success without validation, noisy glossary growth, and copying the old EPUB
2-style exporter unchanged. EPUB output should target EPUB 3.3 and run EPUBCheck when available.

## Key Findings

### Recommended Stack

Use Python 3.13.13 with uv. Use HTTPX for normal crawling, Beautiful Soup with lxml for
extraction, optional Playwright Chromium fallback for rendered pages, Pydantic for file
contracts, PyYAML for profiles/styles, and chardet for encoding fallback. Use standard-library
ZIP creation for canonical EPUB 3.3 output, EPUBCheck for conformance, and Calibre
`ebook-convert` only for AZW3/MOBI/PDF conversion.

### Expected Features

**Must have:**
- Four project-local skills: crawl, translate, QA, export.
- New-book workspace initialization and resumable per-chapter state.
- HTTP crawl, browser fallback, profile validation, and raw-review checkpoint.
- YAML style support with default `tien_hiep`.
- Automatic initial glossary and progressive merge after every chapter.
- Strictly sequential context-isolated translation with retry-stop-resume behavior.
- Deterministic QA report and approval checkpoint.
- EPUB 3.3 output with optional Calibre conversions.

**Should have after validation:**
- Additional bundled styles.
- Targeted retranslation workflows based on QA findings.
- Larger reusable crawl-profile library.
- Optional second review worker only if deterministic QA proves insufficient.

**Defer:**
- UI/API shell.
- Legacy workspace migration.
- First-class Antigravity and Claude Code adapters.
- Adjacent-chapter concurrency.

### Architecture Approach

Skills are orchestrators; Python helpers are state authorities. A translation worker receives
absolute paths for one chapter, the prior translated chapter, the active style, and glossary. It
writes staged output and compact result metadata. The helper validates, atomically promotes,
advances per-chapter state, and merges safe glossary proposals before the skill dispatches the
next chapter.

### Critical Pitfalls

1. **Silent crawl corruption** - validate counts, duplicates, titles, sampled body lengths, and
   residue before user approval.
2. **Context loss through adjacent concurrency** - keep v1 translation strictly sequential.
3. **Main-agent context flooding** - pass paths to isolated workers, never full chapters through
   the orchestrator.
4. **Trusting worker success** - stage, validate, then promote atomically.
5. **Unsafe glossary evolution** - preserve canonical mappings and report conflicts.
6. **EPUB 2-style export migration** - implement EPUB 3.3 navigation and metadata, then validate
   with EPUBCheck.

## Implications for Roadmap

### Phase 1: Workspace Contracts and Skill Skeletons
**Rationale:** Every later phase needs stable schemas and command contracts.
**Delivers:** Pydantic models, atomic writes, new workspace layout, default style, and skill
skeletons.

### Phase 2: Crawl and Raw Review Gate
**Rationale:** Translation quality starts with trustworthy source text.
**Delivers:** HTTP crawler, encoding fallback, domain profiles, book overrides, Playwright
fallback, crawl report, and approval marker.

### Phase 3: Glossary Lifecycle
**Rationale:** Translation should start with stable names and safely evolve terms.
**Delivers:** Initial glossary proposals, validated CSV merge, conflict reporting, and snapshots.

### Phase 4: Sequential Agent-Native Translation
**Rationale:** This is the core value and depends on stable workspace, crawl, and glossary
contracts.
**Delivers:** `$translate-book`, one-chapter worker protocol, staged promotion, retries, stop,
and resume.

### Phase 5: QA Review Gate
**Rationale:** Export must depend on an inspectable quality report.
**Delivers:** Deterministic report and explicit QA approval marker.

### Phase 6: EPUB 3.3 and Format Conversion
**Rationale:** Export consumes only approved translations and can remain deterministic.
**Delivers:** EPUB 3.3 assembly, ZIP invariant checks, EPUBCheck integration, and Calibre
conversion to AZW3/MOBI/PDF.

### Phase Ordering Rationale

- State contracts come first because every expensive workflow step must be recoverable.
- Crawl precedes glossary and translation because invalid raw input poisons all later work.
- Glossary precedes translation because chapter 1 already needs canonical terms.
- QA precedes export because the ebook is a reviewed deliverable.

### Research Flags

Phases likely needing deeper planning research:
- **Phase 2:** profile schema, JavaScript fallback, and CAPTCHA/login detection need careful
  fixture design.
- **Phase 4:** native Codex worker protocol and retry/resume semantics are the central product
  risk.
- **Phase 6:** EPUB 3.3 conformance should be checked against W3C rules and EPUBCheck behavior.

Phases with standard patterns:
- **Phase 1:** Pydantic models and atomic file replacement.
- **Phase 3:** CSV proposal merge with validation and conflict reporting.
- **Phase 5:** deterministic report generation.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Package versions verified against official PyPI pages and tool docs |
| Features | HIGH | Derived from explicit user scope and old application behavior |
| Architecture | HIGH | Boundaries are narrow and match the selected hybrid model |
| Pitfalls | HIGH | Supported by old repository implementation lessons and official EPUB rules |

**Overall confidence:** HIGH

### Gaps to Address

- Confirm the exact Codex worker invocation contract available when `$translate-book` is
  implemented.
- Decide whether EPUBCheck is an optional local prerequisite or a CI-installed verification
  dependency.
- Build representative crawl fixtures from the user's real target domains during Phase 2.

## Sources

### Primary

- `.planning/PROJECT.md`
- https://www.python.org/downloads/
- https://docs.astral.sh/uv/concepts/projects/dependencies/
- https://pypi.org/project/httpx/
- https://pypi.org/project/playwright/
- https://playwright.dev/python/docs/intro
- https://pypi.org/project/pydantic/
- https://pypi.org/project/pydantic-settings/
- https://www.w3.org/TR/epub-33/
- https://github.com/w3c/epubcheck
- https://manual.calibre-ebook.com/generated/en/ebook-convert.html

### Local Reference

- `D:\latuan\Programming\dich-truyen-tien-hiep\README.md`
- `D:\latuan\Programming\dich-truyen-tien-hiep\docs\ARCHITECTURE.md`
- `D:\latuan\Programming\dich-truyen-tien-hiep\.agents\skills\translate-error-chapters\SKILL.md`

---
*Research completed: 2026-05-31*
*Ready for roadmap: yes*
