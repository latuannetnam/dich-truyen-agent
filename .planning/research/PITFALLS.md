# Pitfalls Research

**Domain:** Codex-first agent-native Chinese-to-Vietnamese novel translation workflow
**Researched:** 2026-05-31
**Confidence:** HIGH

## Critical Pitfalls

### Pitfall 1: Silent Crawl Corruption

**What goes wrong:** A selector finds navigation links, ads, incomplete chapter lists, or empty
content. Translation proceeds and wastes time on bad raw inputs.

**Why it happens:** A scraper treats "some matches" as success and skips domain-specific
validation.

**How to avoid:** Validate minimum chapter count, duplicate URLs, title samples, content-length
samples, encoding warnings, and navigation/ad residue. Require user raw review before translation.

**Warning signs:** Suspiciously low chapter count, repeated chapter titles, many files below a
content-length threshold, or raw text dominated by site chrome.

**Phase to address:** Crawl foundation phase.

---

### Pitfall 2: Translating Ahead of Context

**What goes wrong:** Adjacent chapters are translated concurrently and later chapters use stale
or missing Vietnamese context, producing pronoun and terminology drift.

**Why it happens:** Throughput optimization is applied before defining the quality contract.

**How to avoid:** Translate strictly sequentially in v1. Promote chapter `N` before dispatching
chapter `N+1`.

**Warning signs:** Different translations for the same relationship terms, inconsistent names,
or workers reading missing previous-chapter files.

**Phase to address:** Translation orchestration phase.

---

### Pitfall 3: Main-Agent Context Flooding

**What goes wrong:** The orchestrator reads raw chapters and full translated chapters directly,
eventually losing instructions or exceeding context limits.

**Why it happens:** A worker protocol returns content rather than paths and compact metadata.

**How to avoid:** Pass absolute paths to isolated workers. Return only result metadata and keep
full chapter text on disk.

**Warning signs:** Large chapter bodies appear in orchestration history or retries become
inconsistent late in a long run.

**Phase to address:** Translation orchestration phase.

---

### Pitfall 4: Trusting Worker Success

**What goes wrong:** The orchestrator advances state even though the worker wrote an empty,
partial, malformed, or wrong-path file.

**Why it happens:** Worker output is treated as authoritative.

**How to avoid:** Write to staging, validate deterministically, then promote atomically. Check
expected path, title header, non-empty body, residual Chinese text, and structured result schema.

**Warning signs:** Missing translated files despite `translated` state, zero-byte files, or
chapter state that points to another index.

**Phase to address:** Translation orchestration phase.

---

### Pitfall 5: Glossary Drift and Unsafe Merge

**What goes wrong:** New worker-proposed terms overwrite existing canonical translations or add
noisy fragments, making later chapters less consistent.

**Why it happens:** Progressive glossary updates are merged without schema validation,
deduplication, or conflict reporting.

**How to avoid:** Merge proposals deterministically. Preserve existing canonical mappings by
default, deduplicate by Chinese term, and report conflicts for later review.

**Warning signs:** Glossary grows rapidly with one-character noise, existing translations change
silently, or the same Chinese term maps to multiple Vietnamese forms.

**Phase to address:** Glossary lifecycle phase.

---

### Pitfall 6: EPUB Looks Valid but Is Not EPUB 3.3-Conformant

**What goes wrong:** Ebook readers open the file, but navigation or metadata is non-conformant.
The old exporter can encourage copying EPUB 2-style NCX-only output.

**Why it happens:** ZIP creation is mistaken for EPUB conformance.

**How to avoid:** Include the uncompressed first `mimetype` entry, `META-INF/container.xml`,
EPUB 3 package metadata including `dcterms:modified`, an XHTML navigation document with one TOC
nav, and EPUBCheck validation.

**Warning signs:** EPUBCheck errors, missing table of contents on readers, or only `toc.ncx`
exists.

**Phase to address:** Export phase.

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| One huge mutable `book.json` | Easy initial implementation | Expensive rewrites and corruption risk | Never for the new schema |
| Profile edits without validation | Faster domain support | Shared domain regressions | Never |
| Browser fetch for every page | Uniform crawler code | Slow crawl and harder debugging | Only for domains proven to require rendering |
| Automatic literary QA fixes | Fewer manual steps | Silent meaning changes | Only for separately approved narrow formatting fixes |
| Worker writes directly to promoted output | Fewer file operations | Partial output appears complete | Never |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| HTTPX | Retry permanent 403/404 responses repeatedly | Retry timeouts and transient failures; stop on permanent or anti-bot signals |
| Playwright | Forget browser binary installation | Keep it optional and document `playwright install chromium` |
| YAML | Load untrusted YAML with unsafe loader | Use `safe_load`, then validate with Pydantic |
| Calibre | Make Calibre mandatory for EPUB | Build canonical EPUB directly; use Calibre only for conversion |
| EPUB ZIP | Compress or reorder `mimetype` | Write it first and uncompressed |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Passing chapter text through orchestrator prompts | Context growth and instruction drift | Pass paths; keep text in isolated workers | Long books or large chapters |
| Refitting glossary relevance from all raw text after every chapter | Translation pauses increase over time | Start simple; add bounded or incremental indexing only if needed | Hundreds to thousands of chapters |
| Rewriting a shared manifest after each state transition | Slow writes and corruption surface | Per-chapter atomic state files | Large books |
| Browser automation for static sites | Crawling is unnecessarily slow | HTTP-first transport strategy | Any multi-chapter crawl |

## Security and Safety Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Attempting CAPTCHA bypass | Brittle behavior and questionable automation | Stop and ask for user action |
| Allowing arbitrary worker output paths | Writing outside the intended book workspace | Resolve and verify paths stay inside the book directory |
| Unsafe YAML parsing | Code execution from malicious YAML tags | `yaml.safe_load` plus schema validation |
| Overwriting source raw files during cleanup | Irrecoverable loss of crawl evidence | Treat raw files as immutable after crawl approval |
| Running Calibre conversion on arbitrary external paths | Unexpected file access | Restrict conversion input to generated workspace EPUB |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| No crawl report | User cannot judge whether raw extraction is trustworthy | Show counts, samples, warnings, and explicit approval gate |
| Resume without explaining stop reason | User does not know how to recover | Persist last error and print the exact resume command |
| QA report with only counts | User cannot inspect problems efficiently | Include chapter index, issue type, expected value, and context |
| Export before QA approval | Ebook appears final too early | Enforce checkpoint marker |

## "Looks Done But Is Not" Checklist

- [ ] **Crawl:** Verify sampled raw files contain chapter content rather than page chrome.
- [ ] **Translation:** Verify state advances only after staged-file promotion.
- [ ] **Glossary:** Verify conflicts are reported rather than silently overwritten.
- [ ] **QA:** Verify missing chapters, empty files, Chinese leftovers, glossary drift, and title
      formatting are covered.
- [ ] **EPUB:** Verify EPUB 3 navigation and `dcterms:modified`, not only ZIP structure.
- [ ] **Conversion:** Verify EPUB succeeds without Calibre and other formats fail clearly when
      Calibre is absent.

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Bad crawl rule | MEDIUM | Keep raw report, repair book override, recrawl into staging, compare, approve |
| Failed translation | LOW | Inspect persisted error, correct input or prompt contract, resume from failed chapter |
| Bad progressive glossary proposal | LOW | Restore glossary snapshot, remove proposal, resume next chapter |
| Invalid EPUB | LOW | Run EPUBCheck, fix deterministic assembler, regenerate from promoted translations |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Silent crawl corruption | Crawl foundation | Fixture domains and report assertions |
| Main-agent context flooding | Translation orchestration | Worker protocol tests and skill review |
| Translating ahead of context | Translation orchestration | Assert only next sequential chapter dispatches |
| Unsafe glossary merge | Glossary lifecycle | Conflict and deduplication tests |
| Weak QA visibility | QA gate | Report fixture tests |
| Non-conformant EPUB | Export | ZIP invariant tests and EPUBCheck |

## Sources

- `.planning/PROJECT.md` - approved scope and review gates
- `D:\latuan\Programming\dich-truyen-tien-hiep\docs\ARCHITECTURE.md` - old application lessons
- `D:\latuan\Programming\dich-truyen-tien-hiep\.agents\skills\translate-error-chapters\SKILL.md` - prior worker isolation lessons
- https://www.w3.org/TR/epub-33/ - EPUB 3.3 packaging and navigation requirements
- https://github.com/w3c/epubcheck - official validation tool
- https://playwright.dev/python/docs/intro - browser automation installation

---
*Pitfalls research for: Codex-first agent-native novel translation workflow*
*Researched: 2026-05-31*
