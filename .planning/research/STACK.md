# Stack Research

**Domain:** Codex-first agent-native Chinese-to-Vietnamese novel translation workflow
**Researched:** 2026-05-31
**Confidence:** HIGH

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | 3.13.13 | Deterministic helper scripts and package code | The repository already targets Python 3.13. Python 3.14.5 is current, but staying on the latest 3.13 patch reduces compatibility risk while preserving a modern runtime. |
| uv | Current installed tool | Dependency locking and command execution | The repository already uses `pyproject.toml`, `.python-version`, and `uv.lock`. Keep standard dependency declarations and use `uv add` / `uv run`. |
| Codex skills | Project-local Markdown skills | User-facing orchestration | The product is operated through `$crawl-book`, `$translate-book`, `$check-translation`, and `$export-book`, with helpers beneath the skills. |
| Standard library `zipfile` | Python 3.13 | EPUB 3.3 packaging | Direct assembly is deterministic and avoids making Calibre mandatory for canonical EPUB output. |
| Calibre `ebook-convert` | 9.9.x compatible CLI | Optional format conversion | Use only after canonical EPUB generation to produce AZW3, MOBI, or PDF. |

Python.org lists Python 3.14.5 as the latest release and Python 3.13.13 as the latest
3.13 patch on 2026-05-31. The conservative v1 recommendation is Python 3.13.13 because
the scaffold already pins the 3.13 line and Playwright's current PyPI classifiers explicitly
include Python 3.13.

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

```toml
[project]
requires-python = ">=3.13,<3.14"
dependencies = [
  "beautifulsoup4>=4.14,<5",
  "chardet>=7.4,<8",
  "httpx>=0.28,<1",
  "lxml>=6.1,<7",
  "pydantic>=2.13,<3",
  "pydantic-settings>=2.14,<3",
  "pyyaml>=6.0,<7",
]

[project.optional-dependencies]
browser = [
  "playwright>=1.60,<2",
]

[dependency-groups]
dev = [
  "pytest>=9.0,<10",
  "pytest-asyncio>=1.4,<2",
  "ruff>=0.15,<1",
]
```

Use bounds as implementation-time guidance. Let `uv.lock` capture exact resolved versions.

## Installation

```bash
uv add "httpx>=0.28,<1" "beautifulsoup4>=4.14,<5" "lxml>=6.1,<7"
uv add "pydantic>=2.13,<3" "pydantic-settings>=2.14,<3"
uv add "pyyaml>=6.0,<7" "chardet>=7.4,<8"
uv add --optional browser "playwright>=1.60,<2"
uv add --dev "pytest>=9,<10" "pytest-asyncio>=1.4,<2" "ruff>=0.15,<1"
uv run playwright install chromium
```

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
| Direct OpenAI API calls for translation | This recreates the old application rather than using coding-agent-native workers. | Codex skill orchestration and context-isolated translation workers. |
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

---
*Stack research for: Codex-first agent-native novel translation workflow*
*Researched: 2026-05-31*
