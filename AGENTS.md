<!-- GSD:project-start source:PROJECT.md -->

## Project

**Dich Truyen Agent**

Dich Truyen Agent is an Antigravity-first, agent-native workflow for crawling Chinese novels,
translating them into Vietnamese, checking translation quality, and exporting ebooks. It
rebuilds the useful behavior of the existing `D:\latuan\Programming\dich-truyen-tien-hiep`
application around coding-agent skills and small deterministic Python helpers instead of a
long-running application UI or API.

The primary user is the repository owner operating the workflow interactively through Antigravity.
The design keeps file contracts and helper scripts portable so adapters for Codex or
Claude Code can be added later.

**Core Value:** Produce resumable, high-quality Vietnamese novel translations through explicit review
checkpoints while keeping each agent task small, inspectable, and recoverable.

### Constraints

- **Runtime**: Antigravity is the supported v1 agent runtime - file contracts and helpers must avoid
  unnecessary Antigravity-specific coupling so adapters can be added later.

- **Interface**: User-facing workflows are Antigravity skills - no UI or API server in v1.
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
<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->

## Technology Stack

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | 3.13.13 | Deterministic helper scripts and package code | The repository already targets Python 3.13. Python 3.14.5 is current, but staying on the latest 3.13 patch reduces compatibility risk while preserving a modern runtime. |
| uv | Current installed tool | Dependency locking and command execution | The repository already uses `pyproject.toml`, `.python-version`, and `uv.lock`. Keep standard dependency declarations and use `uv add` / `uv run`. |
| Antigravity skills | Project-local Markdown skills | User-facing orchestration | The product is operated through `$crawl-book`, `$translate-book`, `$check-translation`, and `$export-book`, with helpers beneath the skills. |
| Standard library `zipfile` | Python 3.13 | EPUB 3.3 packaging | Direct assembly is deterministic and avoids making Calibre mandatory for canonical EPUB output. |
| Calibre `ebook-convert` | 9.9.x compatible CLI | Optional format conversion | Use only after canonical EPUB generation to produce AZW3, MOBI, or PDF. |

### Runtime Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `httpx` | 0.28.1 | Async HTTP fetches with timeouts, redirects, and retries | Default crawler transport for static HTML. Use the latest stable release, not the `1.0.dev*` prereleases. |
| `playwright` | 1.60.0 | Headless browser automation | Optional browser fallback when HTTP HTML lacks rendered chapter links or content. Install browser binaries separately with `playwright install`. |
| `beautifulsoup4` | 4.14.3 | Tolerant HTML parsing and CSS selection | Parse index and chapter HTML snapshots. |
| `lxml` | 6.1.1 | Fast parser backend | Use as Beautiful Soup's parser backend. |
| `pydantic` | 2.13.4 | Validate manifests, profiles, worker results, and reports | Use at every file-contract boundary. |
| `pydantic-settings` | 2.14.1 | Environment and local configuration | Use for crawler delay, retry, Calibre path, and workspace defaults. |
| `PyYAML` | 6.0.3 | Custom style and crawl-profile YAML | Use `safe_load`; validate parsed data with Pydantic. |
| `chardet` | 7.4.3 | Chinese page encoding detection | Use only when response headers and explicit profile encoding are insufficient. |

### Development Tools

| Tool | Version | Purpose | Notes |
|------|---------|---------|-------|
| `pytest` | 9.0.3 | Unit and integration testing | Separate offline tests from network/browser integration tests. |
| `pytest-asyncio` | 1.4.0 | Async helper testing | Required for crawler helper tests. |
| `ruff` | 0.15.15 | Linting and formatting | Keep the repository small and consistently formatted. |
| EPUBCheck | 5.3.0 | EPUB conformance verification | Run after EPUB assembly when the external CLI is installed; also test container invariants in Python. |

## Dependency Layout

## Installation

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| HTTPX first, Playwright fallback | Playwright for every fetch | Only if most target sites are JavaScript-rendered and browser startup overhead no longer matters. |
| Pydantic file contracts | Ad hoc dictionaries | Only for throwaway experiments; not acceptable for persisted book state or agent results. |
| Direct EPUB 3.3 assembly | Calibre-only EPUB generation | Use Calibre-only generation if maintaining EPUB conformance becomes more expensive than expected. |
| Standard library CLI entry points | A full web/API framework | Add a framework only when a non-agent UI becomes a real requirement. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| Direct OpenAI API calls for translation | This recreates the old application rather than using coding-agent-native workers. | Antigravity skill orchestration and context-isolated translation workers. |
| HTTPX `1.0.dev*` prereleases | They are prereleases and add unnecessary migration risk. | Stable `httpx` 0.28.1 range. |
| Playwright as the default crawler | Browser startup is slower and makes simple static sites harder to debug. | HTTP first, browser fallback after validation failure. |
| EPUB 2-only NCX output | EPUB 3.3 requires an EPUB navigation document; NCX is legacy. | EPUB 3.3 package with XHTML nav and optional compatibility NCX only if needed. |
| Regex editing of shared JSON files | Partial writes and malformed state are difficult to recover from. | Validated models plus atomic temp-file replacement. |

## Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| Python 3.13.13 | Current scaffold | Keep `.python-version` on `3.13` and resolve exact patch through uv. |
| Playwright 1.60.0 | Python >=3.9 | PyPI classifiers explicitly include Python 3.13; install Chromium binaries separately. |
| Pydantic 2.13.4 | Python >=3.9 | Use Pydantic v2 APIs only. |
| pydantic-settings 2.14.1 | Python >=3.10 | Compatible with the selected Python line. |
| EPUBCheck 5.3.0 | EPUB 2 and EPUB 3 | Use to validate EPUB 3.3 output. |

## Sources

- https://www.python.org/downloads/ - current Python releases
- https://docs.astral.sh/uv/concepts/projects/dependencies/ - uv dependency fields and commands
- https://pypi.org/project/httpx/ - stable HTTPX release and async features
- https://pypi.org/project/playwright/ - Playwright release and Python support
- https://playwright.dev/python/docs/intro - browser installation and general-purpose automation
- https://pypi.org/project/pydantic/ - current Pydantic release
- https://pypi.org/project/pydantic-settings/ - current settings package release
- https://pypi.org/project/beautifulsoup4/ - current Beautiful Soup release
- https://pypi.org/project/lxml/ - current lxml release
- https://pypi.org/project/PyYAML/ - current PyYAML release
- https://pypi.org/project/chardet/ - current chardet release
- https://pypi.org/project/pytest/ - current pytest release
- https://pypi.org/project/pytest-asyncio/ - current pytest-asyncio release
- https://pypi.org/project/ruff/ - current Ruff release
- https://www.w3.org/TR/epub-33/ - EPUB 3.3 conformance rules
- https://github.com/w3c/epubcheck - official EPUB conformance checker
- https://manual.calibre-ebook.com/generated/en/ebook-convert.html - Calibre conversion CLI

<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->

## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->

## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->

## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, `.agent/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->

## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:

- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

## Windows Sandbox ACL Troubleshooting

When running pytest inside an Antigravity Windows sandbox, use:

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run pytest
```

Do not pass `--basetemp`. Pytest normally creates session directories, `tmp_path` children, and
cache staging directories with mode `0o700`. On Windows this becomes a protected owner-only
DACL that drops the inherited Antigravity workspace capability SID. The restricted sandbox token
then receives `WinError 5: Access is denied` when reopening a directory it just created.

This is not primarily a parent-directory ACL problem. Pre-creating writable parents such as
`C:\tmp` does not fix children recreated with owner-only ACLs. The Windows-only compatibility
shim in `tests/conftest.py` creates pytest temporary directories with inherited ACLs and
initializes `.pytest_cache` before pytest uses its inaccessible staging path. If pytest is
upgraded, rerun the suite from a fresh subagent because the shim patches private pytest helpers.

## Windows Console UTF-8 & Unicode Troubleshooting

When running Python CLI scripts or tests that output Sino-Vietnamese unicode characters on Windows, the console may crash with a `UnicodeEncodeError` (e.g. `'charmap' codec can't encode...`) if the default system codepage (like CP1252 or CP936) is active. 

To run scripts successfully with UTF-8 unicode encoding, prepend the command with the `PYTHONUTF8` environment variable:

```powershell
$env:PYTHONUTF8=1
uv run python main.py <command>
```

Alternatively, configure the standard IO encoding directly in the terminal session:

```powershell
$env:PYTHONIOENCODING="utf-8"
uv run python main.py <command>
```

<!-- GSD:profile-start -->

## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
