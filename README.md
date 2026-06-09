# Dich Truyen Agent

Dich Truyen Agent is a coding-agent native workflow designed to crawl Chinese web novels, translate them sequentially into high-quality literary Vietnamese, verify translation quality through deterministic QA gates, and export valid, conformant EPUB 3.3 ebooks and Calibre format derivatives.

Rather than relying on a heavy long-running application UI or centralized servers, Dich Truyen Agent is operated interactively through lightweight, deterministic Python CLI helpers and local orchestration skills. The codebase is fully optimized for coding-agent runtimes (such as Antigravity, Claude Code, and Codex).

---

## Core Values & Constraints

- **Resumability & Atomicity:** Every workflow step writes files atomically using temporary files and directory states, ensuring that interrupted execution preserves all progress.
- **High-Quality Continuity:** Chapters are translated strictly in order; chapter $N$ receives the finished translation of chapter $N-1$ as context to ensure stylistic consistency and pronoun cohesion.
- **Strict Gated Checkpoints:** Downstream steps are blocked by secure cryptographic checkpoint gates. You cannot translate before crawl approval, and you cannot export before QA approval.
- **Token Efficiency:** Network crawling and batch executions run autonomously.Runtimes receive compact result manifests rather than verbose streaming content.
- **Standard Conformance:**Canonical ebooks are assembled in compliance with the **EPUB 3.3 specification**, verified via EPUBCheck, and converted into AZW3, MOBI, and PDF formats using Calibre.

---

## Directory Structure

A book workspace is managed under `books/<book-slug>/` and is organized as follows:

```text
books/<book-slug>/
├── book.yaml               # Immutable book metadata (Title, Author, Source URL)
├── chapters.yaml           # Chapter catalog mapping IDs to files and URLs
├── state.yaml              # Active chapter stage records (Raw & Translation statuses)
├── style.yaml              # Local translation style guide snapshot (Tien Hiep, etc.)
├── glossary.yaml           # Terminology glossary (Chinese -> Vietnamese)
├── raw/                    # Downloaded Chinese raw text files
├── translations/           # Promoted Vietnamese translation files
├── staging/                # Staged translation drafts and progressive proposals
├── checkpoints/            # Cryptographic approvals (crawl-approved, qa-approved)
└── reports/
    ├── crawl.yaml          # Detailed crawler verification statistics
    ├── qa-report.yaml      # Quality Assurance structural, length, and residue findings
    ├── glossary-conflicts.yaml # Merge conflicts log
    └── results/            # Persisted CLI execution results metadata
```

---

## Environment Setup

Ensure you have **Python 3.13** and **uv** installed.

### 1. Install Dependencies
```powershell
uv sync --all-groups
```

### 2. Configure System Paths (Optional)
If running EPUB validations and Calibre derivative format conversions, configure your system environment paths:
```powershell
# Path to your epubcheck.jar file or folder (Required for export)
$env:DICH_TRUYEN_EPUBCHECK_PATH = "$PWD\tools\epubcheck-5.3.0"

# Path to Calibre's ebook-convert executable (Optional)
$env:DICH_TRUYEN_CALIBRE_PATH = "C:\Program Files\Calibre2\ebook-convert.exe"
```

### 3. Run Automated Tests
Verify that your installation is healthy by running the complete test suite:
```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run pytest
```

---

## Harness-Based Usage Workflow

The workspace is operated through generated harness adapters rather than one
runtime-specific skill set. The shared architecture keeps one canonical source
of truth while still allowing each coding-agent runtime to use its native tools
for commands, bounded file reads, and subagent delegation.

### Harness Adapter Architecture

- Canonical source lives in `.harness/source/`.
- Generated runtime adapters are committed so every harness can discover them
  without running setup first.
- Adapter names are prefixed to avoid duplicate or ambiguous discovery:
  `ag-*` for Antigravity, `cc-*` for Claude Code, `oc-*` for OpenCode, and
  `codex-*` for Codex.
- Root guide files are generated from shared main-agent logic:
  `AGENTS.md` contains the cross-harness guide and `CLAUDE.md` contains the
  Claude-specific panel.
- OpenCode duplicate-discovery protection is declared in `opencode.json`; only
  the `oc-*` pipeline skills remain active for OpenCode.

Generated adapter locations:

```text
.agent/skills/ag-*          # Antigravity skills
.agent/agents/ag_*          # Antigravity subagents
.claude/skills/cc-*         # Claude Code skills
.claude/agents/cc_*         # Claude Code subagents
.opencode/skill/oc-*        # OpenCode skills
.opencode/agent/oc-*        # OpenCode subagents
.codex/skills/codex-*       # Codex skills
.codex/agents/codex_*       # Codex subagents
```

### Skill Name Matrix

| Phase | Antigravity | Claude Code | OpenCode | Codex |
|---|---|---|---|---|
| Crawl | `ag-crawl-book` | `cc-crawl-book` | `oc-crawl-book` | `codex-crawl-book` |
| Translate | `ag-translate-book` | `cc-translate-book` | `oc-translate-book` | `codex-translate-book` |
| QA | `ag-check-translation` | `cc-check-translation` | `oc-check-translation` | `codex-check-translation` |
| Export | `ag-export-book` | `cc-export-book` | `oc-export-book` | `codex-export-book` |

### Step 1: Initialize the Workspace

The user instructs the agent to initialize a clean workspace:

> **User:** Please initialize a workspace for the book "Kiem Lai" with slug
> `jian-lai` and source URL `https://example.com/jian-lai`.

The agent uses the CLI helper:

```powershell
$env:PYTHONUTF8=1
uv run python main.py init-book --slug jian-lai --title "Kiem Lai" --source-url "https://example.com/jian-lai"
```

### Step 2: Crawl and Review Gate

Trigger the crawl skill for the active harness:

```text
$ag-crawl-book books/jian-lai/
$cc-crawl-book books/jian-lai/
$oc-crawl-book books/jian-lai/
$codex-crawl-book books/jian-lai/
```

The agent executes the crawler, creates `reports/crawl.yaml`, and waits for the
user to approve the raw crawl evidence:

```powershell
$env:PYTHONUTF8=1
uv run python main.py approve-crawl --workspace books/jian-lai
```

### Step 3: Glossary Generation and Lifecycle

After crawl approval, the agent initializes and evolves `glossary.yaml` as
translation proceeds. Users can edit names or terms directly in the glossary or
ask the agent to lock canonical translations for important terms.

During translation, `prepare-translation-context` writes a bounded
`staging/chuong-NNNN-glossary-context.yaml` file for the next chapter. It lists
glossary terms found in that raw chapter and any rejected aliases from unresolved
conflict records. `promote-chapter` blocks before writing to `translations/` if
the staged draft proposes a conflicting mapping or uses a rejected alias. QA also
treats unresolved glossary conflicts as blocking findings.

### Step 4: Sequential Agent Translation

Trigger the translate skill for the active harness:

```text
$ag-translate-book books/jian-lai/
$cc-translate-book books/jian-lai/
$oc-translate-book books/jian-lai/
$codex-translate-book books/jian-lai/
```

Translation is always sequential. The main agent checks progress, delegates
bounded batches to coordinator subagents where supported, and isolates chapter
file reading inside translator subagents. Chapter `N` receives the completed
Vietnamese output of Chapter `N-1` as continuity context.

If transient failures exhaust retries, translation pauses safely at the last
promoted chapter. Running the same harness-prefixed translate skill resumes from
the next pending chapter.

### Step 5: Quality Assurance Auditing

Trigger the QA skill for the active harness:

```text
$ag-check-translation books/jian-lai/
$cc-check-translation books/jian-lai/
$oc-check-translation books/jian-lai/
$codex-check-translation books/jian-lai/
```

The agent scans for structural gaps, missing or empty chapters, Chinese residue,
formatting anomalies, abnormal length ratios, and glossary conflicts. If the QA
report is accepted, approve the QA checkpoint:

```powershell
$env:PYTHONUTF8=1
uv run python main.py approve-qa --workspace books/jian-lai
```

### Step 6: EPUB 3.3 Ebook Export

Trigger the export skill for the active harness:

```text
$ag-export-book books/jian-lai/ epub,azw3,mobi,pdf
$cc-export-book books/jian-lai/ epub,azw3,mobi,pdf
$oc-export-book books/jian-lai/ epub,azw3,mobi,pdf
$codex-export-book books/jian-lai/ epub,azw3,mobi,pdf
```

The agent validates the QA checkpoint, compiles the canonical EPUB 3.3 ebook,
runs EPUBCheck, and derives optional Calibre formats. Outputs are saved under
`books/jian-lai/exports/`.

### Updating Harness Adapters

Do not edit generated adapter files directly. Update `.harness/source/**`, then
regenerate and verify:

```powershell
$env:PYTHONUTF8=1
uv run python tools/sync_harness_adapters.py
uv run python tools/sync_harness_adapters.py --check
uv run pytest -q
uv run ruff check tools tests src main.py
```

Generated files include a `GENERATED from .harness/source` header. If a generated
file is stale, `tools/sync_harness_adapters.py --check` reports it.

---

## Code Quality & Standards

Code styling is strictly enforced across all Python source and test suites. We use **Ruff** for linting and code formatting:

```powershell
# Check for linting issues
uv run ruff check

# Verify code formatting
uv run ruff format --check
```
