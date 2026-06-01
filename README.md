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
$env:DICH_TRUYEN_EPUBCHECK_PATH = "C:\Users\latuan\tools\epubcheck-5.3.0"

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

## v1 Usage Workflow

Operating the novel workflow consists of five sequential steps guided by separate project-local skills.

### Step 1: Initialize the Book Workspace
Initialize a new book workspace from a Chinese web novel source:
```powershell
uv run python -m dich_truyen_agent.cli init-book --slug jian-lai --title "Kiếm Lai" --source-url "https://example.com/jian-lai"
```

---

### Step 2: Crawl and Review Gate (Crawl Skill)
Download raw chapters using the domain configuration profile:
```powershell
# 1. Batch crawl raw chapters
uv run python -m dich_truyen_agent.cli crawl-book --slug jian-lai --source-url "https://example.com/jian-lai"

# 2. Inspect crawl statistics and approve crawled content, creating the crawl-approved checkpoint
uv run python -m dich_truyen_agent.cli approve-crawl --workspace books/jian-lai
```

---

### Step 3: Glossary Generation & Life Cycle (Glossary Skill)
Evolve a reviewable terms dictionary:
```powershell
# 1. Generate an initial glossary from crawl evidence
uv run python -m dich_truyen_agent.cli generate-glossary --slug jian-lai --chapters 1,2,3

# 2. Lock a terminology mapping manually to protect it from progressive overrides
uv run python -m dich_truyen_agent.cli lock-term --workspace books/jian-lai --term "修炼"
```

---

### Step 4: Sequential Agent Translation (Translate Skill)
Translate chapters sequentially. Runtimes fetch isolated contexts per chapter:
```powershell
# 1. Determine the next pending chapter and load context parameters (style, glossary, predecessor context)
uv run python -m dich_truyen_agent.cli show-translation-progress --workspace books/jian-lai
uv run python -m dich_truyen_agent.cli prepare-translation-context --workspace books/jian-lai --chapter-id 1

# 2. Perform translation and save draft inside staged text. Promote staged translation atomically
# (This steps merges terminology proposals, hashes the output, and updates state.yaml status)
uv run python -m dich_truyen_agent.cli promote-chapter --workspace books/jian-lai --chapter-id 1
```

---

### Step 5: Quality Assurance Auditing (QA Skill)
Enforce a read-only deterministic quality scan across the finished chapters:
```powershell
# 1. Run structural, completeness, Chinese residue, length ratio, and conflict audits
uv run python -m dich_truyen_agent.cli check-translation --workspace books/jian-lai

# 2. Approve findings and generate the cryptographic qa-approved checkpoint gate
uv run python -m dich_truyen_agent.cli approve-qa --workspace books/jian-lai
```

---

### Step 6: EPUB 3.3 & Calibre Format Exports (Export Skill)
Compile canonical digital books once the QA gate is approved:
```powershell
# Compile canonical EPUB 3.3 and optional AZW3/MOBI/PDF derivatives
uv run python -m dich_truyen_agent.cli export-book --workspace books/jian-lai --formats epub,azw3,mobi,pdf
```
Canonical ebooks are written to `books/<book-slug>/exports/`.

---

## Code Quality & Standards

Code styling is strictly enforced across all Python source and test suites. We use **Ruff** for linting and code formatting:

```powershell
# Check for linting issues
uv run ruff check

# Verify code formatting
uv run ruff format --check
```
