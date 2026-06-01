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

## v1 Usage Workflow (Skill-Based)

The workspace is designed to be operated interactively through Antigravity project-local skills rather than raw console scripts. The workflow is a collaborative partnership between the user and the coding-agent, governed by explicit gate checkpoints.

### Step 1: Initialize the Workspace
The user instructs the agent to initialize a clean workspace:
> **User:** Please initialize a workspace for the book "Kiếm Lai" with slug `jian-lai` and source URL `https://example.com/jian-lai`.
> **Agent:** *(Initializes the directory structure, loads default style configs, and sets up chapter state manifests).*

---

### Step 2: Crawl and Review Gate (`crawl-book` Skill)
The user triggers the crawl skill to autonomously download raw novel content:
1. **Trigger Skill:** The user runs `$crawl-book books/jian-lai/`.
2. **Execution:** The agent executes the batch crawler (handling retries, backoffs, and Playwright rendering fallback if static parse fails) and creates `reports/crawl.yaml`.
3. **Approval:** The user reviews the crawl report and instructs the agent to approve the raw content:
   > **User:** The crawl report looks great, please approve the crawl for `books/jian-lai/`.
   > **Agent:** *(Approves checkpoints, creating the cryptographically secure `checkpoints/crawl-approved.yaml` with evidence hashes).*

---

### Step 3: Glossary Generation & Life Cycle
The glossary dictionary is initialized and evolved safely as translation proceeds:
- After crawl approval, the agent automatically initializes `glossary.yaml` and extracts initial vocabulary.
- The user can edit names or terms directly in `glossary.yaml` or lock crucial translations:
  > **User:** Please lock the canonical translation for "修炼" in `books/jian-lai/`.
  > **Agent:** *(Locks term as canonical to protect it from progressive merging).*

---

### Step 4: Sequential Agent Translation (`translate-book` Skill)
The user triggers sequential translation:
1. **Trigger Skill:** The user runs `$translate-book books/jian-lai/`.
2. **Execution:** The agent orchestrator runs sequentially:
   - Fetches isolated chapter context (vocabulary, style rules, and Chapter $N-1$ text).
   - Spawns specialized translator subagents to translate Chapter $N$ without bloating the main chat session context window.
   - Merges chapter-level progressive glossary proposals and atomically promotes translated Vietnamese chapters.
3. **Resumption:** If transient LLM failures exhaust the 3 retries, translation pauses safely. The user can manually inspect the staged draft or glossary mapping and run `$translate-book books/jian-lai/` to resume exactly from the failed chapter.

---

### Step 5: Quality Assurance Auditing (`check-translation` Skill)
The user triggers a read-only quality scan once translation is complete:
1. **Trigger Skill:** The user runs `$check-translation books/jian-lai/`.
2. **Execution:** The agent scans all files for structural gaps (missing/empty chapters), incompleteness (unbalanced quotes, missing ending punctuation), Chinese residue characters/symbols, abnormal Vietnamese-to-Chinese character length ratios, and glossary conflicts.
3. **Approval:** If findings are clean or warnings are accepted, the user directs the agent to approve the QA:
   > **User:** The QA report is acceptable, please approve the QA checkpoint.
   > **Agent:** *(Saves evidence hashes of all translations to `checkpoints/qa-approved.yaml`).*

---

### Step 6: EPUB 3.3 Ebook Export (`export-book` Skill)
The user compiles digital books once the QA gate is approved:
1. **Trigger Skill:** The user runs `$export-book books/jian-lai/ epub,azw3,mobi,pdf`.
2. **Execution:** The agent validates the QA checkpoint, compiles the canonical EPUB 3.3 ebook in-memory, performs mandatory validation checks via EPUBCheck subprocesses, and derives optional Calibre formats (AZW3, MOBI, PDF).
3. **Outputs:** The validated canonical EPUB and Calibre derivatives are saved to `books/jian-lai/exports/`.


---

## Code Quality & Standards

Code styling is strictly enforced across all Python source and test suites. We use **Ruff** for linting and code formatting:

```powershell
# Check for linting issues
uv run ruff check

# Verify code formatting
uv run ruff format --check
```
