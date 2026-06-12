# Dich Truyen Agent

Dich Truyen Agent is a coding-agent native workflow for crawling Chinese web
novels, translating them sequentially into literary Vietnamese, checking
translation quality through deterministic gates, and exporting EPUB 3.3 ebooks
plus optional Calibre derivatives.

The project is operated through lightweight Python CLI helpers and generated
agent harness adapters. It avoids a long-running UI or centralized server, so
the workspace stays local, resumable, and inspectable.

For internal pipeline design, workspace artifacts, checkpoint logic, glossary
consistency gates, and harness adapter generation, see
[ARCHITECTURE.md](ARCHITECTURE.md).

---

## Core Values

- **Resumability and atomicity:** interrupted runs preserve completed work.
- **Sequential continuity:** chapter `N` uses the promoted Vietnamese chapter
  `N-1` as narrative context.
- **Gated checkpoints:** crawl approval is required before translation; QA
  approval is required before export.
- **Token efficiency:** agents receive compact manifests and paths instead of
  bulk-reading whole books into the main context.
- **Standard conformance:** canonical exports target EPUB 3.3 and can be
  validated with EPUBCheck.

---

## Environment Setup

Requirements:

- Python 3.13
- `uv`

Install dependencies:

```powershell
uv sync --all-groups
```

Optional export tools:

```powershell
$env:DICH_TRUYEN_EPUBCHECK_PATH = "$PWD\tools\epubcheck-5.3.0"
$env:DICH_TRUYEN_CALIBRE_PATH = "C:\Program Files\Calibre2\ebook-convert.exe"
```

Optional translation orchestration settings can be placed in project `.env`:

```env
DICH_TRUYEN_TRANSLATION_BATCH_SIZE=10
```

The default translation batch size is `5`. Explicit runtime arguments override
`.env`; `.env` overrides the built-in default.

Run tests:

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
$env:PYTHONUTF8=1
uv run pytest
```

---

## Quick Usage

### 1. Initialize A Book Workspace

```powershell
$env:PYTHONUTF8=1
uv run python main.py init-book --slug <book-slug> --title "<title>" --source-url "<source-url>" [--author "<author>"]
```

This creates `books/<book-slug>/` with metadata, state, style, staging,
translation, report, and checkpoint directories.

### 2. Crawl Raw Chapters

Use the crawl skill for your active harness:

```text
$ag-crawl-book books/<book-slug>/
$cc-crawl-book books/<book-slug>/
$oc-crawl-book books/<book-slug>/
$codex-crawl-book books/<book-slug>/
```

Approve crawl evidence after reviewing `reports/crawl.yaml`:

```powershell
$env:PYTHONUTF8=1
uv run python main.py approve-crawl --workspace books/<book-slug>
```

### 3. Translate Sequentially

Use the translate skill for your active harness:

```text
$ag-translate-book books/<book-slug>/
$cc-translate-book books/<book-slug>/
$oc-translate-book books/<book-slug>/
$codex-translate-book books/<book-slug>/
```

Translation resumes automatically from the next pending chapter. The workflow
translates chapters strictly in order and promotes each successful chapter into
`translations/`.

### 4. Check Translation Quality

```text
$ag-check-translation books/<book-slug>/
$cc-check-translation books/<book-slug>/
$oc-check-translation books/<book-slug>/
$codex-check-translation books/<book-slug>/
```

Approve QA after reviewing `reports/qa-report.yaml`:

```powershell
$env:PYTHONUTF8=1
uv run python main.py approve-qa --workspace books/<book-slug>
```

### 5. Export Ebook Formats

```text
$ag-export-book books/<book-slug>/ epub,azw3,mobi,pdf
$cc-export-book books/<book-slug>/ epub,azw3,mobi,pdf
$oc-export-book books/<book-slug>/ epub,azw3,mobi,pdf
$codex-export-book books/<book-slug>/ epub,azw3,mobi,pdf
```

Outputs are written to `books/<book-slug>/exports/`.

---

## Harness Skill Matrix

| Phase | Antigravity | Claude Code | OpenCode | Codex |
|---|---|---|---|---|
| Crawl | `ag-crawl-book` | `cc-crawl-book` | `oc-crawl-book` | `codex-crawl-book` |
| Translate | `ag-translate-book` | `cc-translate-book` | `oc-translate-book` | `codex-translate-book` |
| QA | `ag-check-translation` | `cc-check-translation` | `oc-check-translation` | `codex-check-translation` |
| Export | `ag-export-book` | `cc-export-book` | `oc-export-book` | `codex-export-book` |

---

## Common CLI Commands

Check a gate:

```powershell
$env:PYTHONUTF8=1
uv run python main.py check-gate --workspace books/<book-slug> --type <crawl-approved|qa-approved>
```

Check translation progress:

```powershell
$env:PYTHONUTF8=1
uv run python main.py show-translation-progress --workspace books/<book-slug>
```

Manually lock a glossary term:

```powershell
$env:PYTHONUTF8=1
uv run python main.py lock-term --workspace books/<book-slug> --term "<Chinese term>"
```

---

## Code Quality

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
$env:PYTHONUTF8=1
uv run pytest
uv run ruff check tools tests src main.py
uv run ruff format --check
```
