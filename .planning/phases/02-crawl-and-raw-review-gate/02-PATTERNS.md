# Phase 02: Crawl and Raw Review Gate - Pattern Map

**Mapped:** 2026-05-31
**Status:** Ready for planning

## Closest Existing Analogs

| New responsibility | Closest local analog | Pattern to preserve |
|--------------------|----------------------|---------------------|
| Strict crawl profile/report models | `src/dich_truyen_agent/models.py` | `PersistedModel` with `extra="forbid"` and model validators |
| Shared/local YAML profile loading | `src/dich_truyen_agent/styles.py` | Load YAML through shared validated boundary; snapshot workspace-local reviewed config |
| Safe persisted report/state writes | `src/dich_truyen_agent/storage.py` | `atomic_write_yaml()` and SHA-256 helpers |
| Workspace-local profile/report paths | `src/dich_truyen_agent/paths.py` | Extend `WorkspacePaths`; keep workspace-relative persisted paths |
| Resume after successful raw chapters | `src/dich_truyen_agent/workspace.py` | Validate catalog/state and completed artifact hashes before trusting resume |
| Explicit crawl approval | `src/dich_truyen_agent/checkpoints.py` | User-triggered helper, report path, evidence hashes, stale evidence blocking |
| Compact crawl CLI result | `src/dich_truyen_agent/cli.py` | Persist `OperationResult` beneath `reports/results/`; print concise summary |
| User-facing crawl workflow | `.codex/skills/crawl-book/SKILL.md` | Skill frontmatter plus deterministic helper boundaries and checkpoints |

## Legacy Reference Extracts

Read-only reference:
`../dich-truyen-tien-hiep/src/dich_truyen/crawler/`

| Legacy module | Reuse concept | Do not copy |
|---------------|---------------|-------------|
| `base.py` | one `httpx.AsyncClient`, redirects, user-agent, timeout, delay | linear backoff and permissive retry classification |
| `pattern.py` | Beautiful Soup CSS selectors, `<br>` paragraph preservation, chapter ID parsing | direct LLM API calls, silent dedupe, whole-body fallback |
| `downloader.py` | sequential download loop and save-after-chapter intent | direct non-atomic writes, continue-after-failure behavior |
| `utils/encoding.py` | Chinese fallback chain | detection-only precedence without HTTP/meta provenance |

## Recommended New Files

| Path | Role | Data flow |
|------|------|-----------|
| `src/dich_truyen_agent/crawl_profiles.py` | shared/local profile loading, validation, promotion | template YAML or workspace override -> `CrawlProfile` |
| `src/dich_truyen_agent/crawler.py` | byte fetch, decode, static parse, validation | URL + profile -> catalog entries or extracted chapter |
| `src/dich_truyen_agent/crawl_batch.py` | retry, delay, browser fallback, stop/resume | catalog + workspace state -> raw files + compact result |
| `src/dich_truyen_agent/crawl_reports.py` | report construction and approval blocker evaluation | workspace + crawl result -> `reports/crawl.yaml` |
| `templates/crawl_profiles/piaotia.com.yaml` | validated shared live-target profile | shared profile loader -> static extraction |
| `tests/fixtures/crawl/` | offline HTML fixtures | deterministic parser and batch tests |

## Concrete Conventions

- Extend `WorkspacePaths` rather than assembling profile/report paths ad hoc.
- Keep raw canonical file writes UTF-8 and atomic.
- Use catalog position as local `chapter_id`; retain the remote URL ID as a source identity field
  if needed. Do not treat remote URL IDs as sequential ordinals.
- Use parsed title ordinal only when reliable enough to raise clear gap/repeat blockers.
- Inject fetcher, sleeper, and browser renderer callables into batch logic for fast offline tests.
- Keep Playwright imports lazy so static-only installs work without the optional browser extra.
- Store full HTML diagnostics only in report or diagnostic files, never in `OperationResult`.

## Live Target Profile

For `piaotia.com`:

| Field | Value |
|-------|-------|
| Index selector | `.centent ul li a` |
| Title selector | `h1` |
| Content selector | `#content` |
| Declared encodings | index `gbk`, chapter `gb2312` |
| Required test limit | `max_chapters=10` |
| Required pacing default | `chapter_delay_seconds=3` |

## Security-Relevant Boundaries

- URL/profile input to outbound HTTP requests
- profile pagination links to same-domain traversal
- external HTML to extracted raw UTF-8 text
- raw file/report mutation to crawl approval validity
- partial approval metadata to downstream full-book gates

