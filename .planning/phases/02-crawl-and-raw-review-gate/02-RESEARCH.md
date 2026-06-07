# Phase 02: Crawl and Raw Review Gate - Research

**Researched:** 2026-05-31
**Status:** Complete

## Research Question

What must be known to plan a deterministic, resumable HTTP-first novel crawler with reusable
profiles, safe browser fallback, compact reports, profile repair, and an explicit raw-content
approval gate?

## Existing Foundation

Phase 1 already provides the boundaries this phase should reuse:

- `models.py` centralizes strict Pydantic persisted models with `extra="forbid"`.
- `storage.py` provides YAML `safe_load`, validated atomic YAML replacement, and SHA-256.
- `workspace.py` preserves valid completed files and blocks inconsistent resume state.
- `checkpoints.py` creates explicit hash-backed approvals and recalculates evidence hashes.
- `cli.py` persists compact `OperationResult` files beneath `reports/results/`.
- `.codex/skills/crawl-book/SKILL.md` is an honest placeholder ready for Phase 2 orchestration.

The old application is a functional reference, not a source schema. Its crawler contains useful
ideas but also behaviors this phase must replace:

- Reuse: async `httpx.AsyncClient`, explicit timeout, redirects, user-agent, encoding handling,
  CSS-selector extraction, per-chapter progress persistence, and request delay.
- Replace: direct LLM API selector discovery, silent URL deduplication, permissive whole-body
  fallback extraction, continuing after failed chapters, and non-atomic JSON progress writes.

## Live Target Findings

Required verification target:
`https://www.piaotia.com/html/8/8717/index.html`

Read-only probes on 2026-05-31 found:

| Property | Observation |
|----------|-------------|
| Index response | HTTP `200`, static HTML, approximately 75 KB |
| Index encoding | Meta tag declares `gbk`; HTTP header is only `text/html` |
| Index selector | `.centent ul li a` |
| Discovered links | `1,274` chapter-like relative links |
| First link | `5588734.html` |
| First chapter title | `第一章 惊蛰` |
| Chapter encoding | Meta tag declares `gb2312` |
| Chapter title selector | `h1` |
| Chapter content selector | `#content` |
| Residue | Navigation, ad scripts, footer blocks, Cloudflare-injected scripts |

Important consequence: URL IDs are not chapter ordinals. The sequence starts
`5588734`, `5588735`, `5588736`, `5590037`, so numeric-gap validation must use a parsed title
ordinal when reliable. URL IDs remain stable source identifiers and duplicate detectors only.

Cloudflare challenge scripts can appear after otherwise valid content. Detection must not block
merely because challenge-related script text exists. Treat CAPTCHA/authentication as blocking
when a blocking response or known challenge page shape prevents valid expected extraction.

## Recommended Architecture

### 1. Persisted Profile Contract

Create strict YAML crawl profiles for shared domain rules and book-local overrides. A profile
needs:

- profile identity and domain
- index URL matching
- index page selectors: title, optional author, chapter links
- optional deterministic pagination/list-section rules
- chapter selectors: title, content, removal selectors
- optional explicit encoding override
- validation thresholds for meaningful body text
- transport hint (`http` by default; browser fallback remains a runtime decision)

Store reusable profiles under `templates/crawl_profiles/<domain>.yaml`. Store a validated local
override in the book workspace, for example `crawl-profile.yaml`. Report which source is active.

Do not hide repairs inside crawler heuristics. A failed validated profile returns diagnostics;
the `$crawl-book` skill coordinates agent-assisted editing of the local YAML override, validates
it, and asks whether to promote it.

### 2. Encoding Precedence

Fetch bytes, then decode deterministically:

1. explicit profile encoding
2. HTTP `Content-Type` charset
3. HTML meta charset / `http-equiv`
4. `chardet.detect(raw_bytes)` fallback
5. bounded fallback chain suitable for Chinese text: `gb18030`, `gbk`, `utf-8`

Normalize `gb2312` and `gbk` carefully. Prefer `gb18030` as the broad Chinese fallback; preserve
the chosen encoding in diagnostics and reports.

Beautiful Soup documentation notes that input bytes are converted to Unicode and that automatic
encoding guesses can be wrong. Perform decoding before extraction so the crawler records which
source selected the encoding.

### 3. HTTP and Retry Layer

Use one reusable `httpx.AsyncClient` per batch with redirects enabled, explicit timeouts, and a
user-agent. HTTPX documents strict default timeouts and distinct connect/read/write/pool timeout
classes. Use explicit crawler settings so results are inspectable.

HTTPX transport retries only cover `ConnectError` and `ConnectTimeout`. Phase 2 requires
recoverable status handling such as `5xx` plus configurable exponential backoff, so implement
retry orchestration in crawler code rather than relying only on `AsyncHTTPTransport(retries=...)`.

Default locked behavior:

- maximum attempts: `3`
- configurable exponential backoff
- fixed post-success chapter delay: `3` seconds by default
- `max_chapters=0`: unlimited body downloads
- nonzero `max_chapters`: discover and validate full catalog, download first `N`

### 4. Extraction and Validation

Parse with `BeautifulSoup(html, "lxml")` and CSS selectors. Keep extraction deterministic and
profile-driven:

- reject duplicate source URLs and duplicate stable IDs
- parse optional chapter ordinals from titles where reliable
- block clear parsed ordinal gaps or repeats
- warn when titles cannot be parsed reliably
- reject empty or below-threshold chapter bodies
- remove configured residue selectors before text normalization
- preserve paragraph boundaries from `<br>` and `<p>`

Do not use generic selector guessing during normal execution. Generic repair belongs to the
agent-assisted local profile workflow after validation failure.

### 5. Browser Fallback

Keep Playwright optional and isolated behind a small adapter. Trigger fallback only when HTTP
returns HTML but validated extraction is empty or clearly incomplete in a way consistent with
missing rendered content. Do not use Playwright as a general retry transport.

Playwright documentation requires browser binaries to be installed separately with
`playwright install`. Tests should use an injected fake renderer; one integration fixture can
exercise the adapter when browser binaries exist.

### 6. Resume and Raw Promotion

Catalog discovery writes immutable `chapters.yaml` plus matching pending raw stage entries in
`state.yaml`. Per chapter:

1. fetch and extract into memory
2. validate non-empty normalized body
3. atomically write UTF-8 canonical `raw/<filename>.txt`
4. compute SHA-256
5. atomically update that chapter's raw `StageRecord`
6. sleep the configured chapter delay

On persistent failure, mark the current chapter raw stage as `error`, persist diagnostics, stop
the batch, and do not crawl later chapters. Resume validates existing completed artifacts through
the Phase 1 workspace service and starts at the first non-completed selected chapter.

### 7. Report and Approval Scope

Add a crawl report persisted under `reports/crawl.yaml` with:

- discovered, selected, completed, failed counts
- `max_chapters` and full/partial scope
- active profile source
- duplicate/gap blockers and warnings
- per-chapter length summaries
- beginning/middle/end excerpts for the selected crawl
- intervention details and diagnostic paths

Extend `CheckpointRecord` with explicit approval scope metadata. The existing approval helper
must hash the report itself plus crawled raw files. A limited test crawl may receive a partial
approval, but later full-book gates must be able to reject it.

## Package Legitimacy Audit

| Package | Source | Status | Why |
|---------|--------|--------|-----|
| `httpx>=0.28,<1` | https://www.python-httpx.org/ | Approved | Async client, connection pooling, redirects, explicit timeout classes |
| `beautifulsoup4>=4.14,<5` | https://www.crummy.com/software/BeautifulSoup/bs4/doc/ | Approved | Tolerant HTML parsing and CSS selectors |
| `lxml>=6.1,<7` | https://lxml.de/ | Approved | Explicit Beautiful Soup parser backend |
| `chardet>=7.4,<8` | https://chardet.readthedocs.io/ | Approved | Fallback Chinese encoding detection |
| `pydantic-settings>=2.14,<3` | https://docs.pydantic.dev/latest/concepts/pydantic_settings/ | Approved | Inspectable environment/local crawler settings |
| `playwright>=1.60,<2` | https://playwright.dev/python/docs/library | Approved optional extra | Browser renderer fallback only |

Use `uv` to update `pyproject.toml` and `uv.lock`. Install Playwright as an optional `browser`
extra and document `uv run playwright install chromium` separately.

## Validation Architecture

Offline pytest coverage should carry the phase:

| Layer | Coverage |
|-------|----------|
| Models and profiles | strict YAML schema, precedence, domain matching, local override reuse, promotion |
| Encoding | explicit/header/meta/chardet precedence and GBK/GB2312 fixtures |
| Static extraction | piaotia-like index and chapter fixtures, duplicate blockers, title ordinal gaps, warnings |
| HTTP batch | `httpx.MockTransport`, timeout/`5xx` retries, exponential backoff spy, fixed delay spy |
| Browser fallback | injected fake renderer used only for rendered-content validation failure |
| Intervention | CAPTCHA/auth page shapes block immediately and preserve diagnostics |
| Resume | completed chapters preserved, failure stops later downloads, resume starts at failed chapter |
| Reports | full/partial scope, blockers/warnings, lengths, representative excerpts |
| Checkpoints | report plus raw hashes, partial scope persistence, stale evidence rejection |
| CLI and skill | compact result files, crawl flags, explicit approval, repair/promotion instructions |

Manual verification remains mandatory for the live target because network availability and site
HTML are external state:

1. crawl `https://www.piaotia.com/html/8/8717/index.html`
2. set `--max-chapters 10`
3. retain default `--chapter-delay-seconds 3`
4. confirm full discovery reports `1,274` links at verification time or investigate live drift
5. confirm exactly `10` raw files and a partial crawl report
6. review report samples and create a partial `crawl-approved` checkpoint explicitly

## Threat Model Notes

Each execution plan needs a `<threat_model>` block. Key Phase 2 threats:

- SSRF or unexpected cross-domain crawling from untrusted URLs or profile pagination rules
- path traversal from domain/profile names or chapter filenames
- tampered shared/local YAML profiles
- silent catalog truncation, deduplication, or gap acceptance
- anti-bot page content promoted as a raw chapter
- stale raw approvals after report or chapter mutation
- accidental full-book consumption of partial approvals
- token leakage through chapter bodies or verbose HTML diagnostics in `OperationResult`

## Planning Recommendation

Preserve the roadmap's three-plan split:

1. profile schema, dependency audit, encoding, deterministic HTTP extraction, and fixtures
2. resumable batch orchestration, retries, delay, Playwright fallback, compact intervention
3. crawl reports, partial approval scope, repair/promotion commands, `$crawl-book`, and live run

This ordering keeps the static deterministic core testable before adding transport fallback and
user-facing workflow orchestration.

## Sources

- https://www.python-httpx.org/api/ - `AsyncClient`, redirects, pooling
- https://www.python-httpx.org/advanced/timeouts/ - explicit timeout classes
- https://www.python-httpx.org/advanced/transports/ - transport retry limits and mock transport
- https://playwright.dev/python/docs/library - async API and installation
- https://playwright.dev/python/docs/browsers - browser binary installation requirement
- https://www.crummy.com/software/BeautifulSoup/bs4/doc/ - parser, selectors, and encoding notes
- https://chardet.readthedocs.io/ - fallback encoding detection
- https://docs.pydantic.dev/latest/concepts/models/ - strict model validation
- https://docs.pydantic.dev/latest/concepts/pydantic_settings/ - settings contracts
- `../dich-truyen-tien-hiep/src/dich_truyen/crawler/` - legacy functional reference

## RESEARCH COMPLETE

