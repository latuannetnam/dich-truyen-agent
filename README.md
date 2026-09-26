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

### 1. Unified Single-Command Novel Run (Recommended)

Run a novel directly from its source URL through crawl, translation, QA, and export in a single command:

```powershell
$env:PYTHONUTF8=1
uv run python main.py orchestrate --url "<source-url>" --slug <book-slug> --style <style> [--limit <N>] [--formats epub,pdf] [-y]
```

- `--style`: Genre style profile (`tien_hiep`, `mat_the`, `do_thi`, `general`).
- `--limit <N>`: Freezes the workspace to the first `N` chapters of the source novel, recording complete source catalog provenance in `reports/source-scope.yaml`.
- `-y`, `--yes`: Clean-only auto-approval policy (auto-approves gates only if there are zero warnings and zero errors).

### 2. Existing Workspace Execution

Run the remaining pipeline or explicit phase bounds on an existing workspace:

```powershell
$env:PYTHONUTF8=1
uv run python main.py orchestrate --workspace books/<book-slug> [--start-at <phase>] [--stop-after <phase>] [-y]
```

Or trigger through the harness-specific orchestrate skill:
```text
$ag-orchestrate-book books/<book-slug>/
$cc-orchestrate-book books/<book-slug>/
$oc-orchestrate-book books/<book-slug>/
$codex-orchestrate-book books/<book-slug>/
```

### 3. Gate Approvals and Resuming

When a crawl or QA report contains warnings:
- **Interactive TTY:** The orchestrator displays the gate summary, report path, report hash, and chapter counts, then prompts `Approve [y/N]?`. Answering `y` continues immediately in the same process.
- **Headless / Non-TTY:** The orchestrator pauses with exit code 2. Inspect reports under `reports/` and resume explicitly:
```powershell
$env:PYTHONUTF8=1
uv run python main.py orchestrate --workspace books/<book-slug> --resume --decision approve
```

### 4. Explicit Workspace Initialization (Advanced / Manual)

If you prefer to initialize a directory before running:

```powershell
$env:PYTHONUTF8=1
uv run python main.py init-book --slug <book-slug> --title "<title>" --source-url "<source-url>" --style <style> [--author "<author>"]
```

### 5. Individual Phase Skills (Thin Compatibility Wrappers)

Individual phase skills delegate directly to `orchestrate --start-at <phase> --stop-after <phase>`:

- **Crawl:** `ag-crawl-book`, `cc-crawl-book`, `oc-crawl-book`, `codex-crawl-book`
- **Translate:** `ag-translate-book`, `cc-translate-book`, `oc-translate-book`, `codex-translate-book`
- **QA:** `ag-check-translation`, `cc-check-translation`, `oc-check-translation`, `codex-check-translation`
- **Export:** `ag-export-book`, `cc-export-book`, `oc-export-book`, `codex-export-book`

Outputs are written to `books/<book-slug>/exports/`.

---

## Harness Skill Matrix

| Phase | Antigravity | Claude Code | OpenCode | Codex |
|---|---|---|---|---|
| Orchestrate | `ag-orchestrate-book` | `cc-orchestrate-book` | `oc-orchestrate-book` | `codex-orchestrate-book` |
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
