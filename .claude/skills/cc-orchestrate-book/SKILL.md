---
name: cc-orchestrate-book
description: "Use when running the orchestrate-book phase of the Chinese-to-Vietnamese novel translation pipeline in the cc harness."
---

<!-- GENERATED from .harness/source by tools/sync_harness_adapters.py. Do not edit directly. -->

# CC-Orchestrate Book

Execute and supervise the deterministic LangGraph Chinese-to-Vietnamese novel translation pipeline across crawl, translation, QA, and export phases.

## Overview

The orchestrator manages the full book lifecycle through deterministic workspace gates and supervised child processes:
- Deterministic code discovers, crawls, verifies staging, promotes chapters, runs QA, and exports ebooks.
- A fresh Antigravity process translates one chapter at a time into isolated attempt-scoped staging.
- LangGraph checkpoints state in SQLite per run (`reports/runs/<run_id>/checkpoint.sqlite`).
- Human approval decisions pause cleanly for review and resume on unchanged evidence.

## CLI Usage

### 1. Full Automated Workflow (Default)

Start or resume an initialized book through the remaining lifecycle (crawl -> translate -> QA -> export):

```powershell
$env:PYTHONUTF8=1
uv run python main.py orchestrate --workspace books/<book-slug>
```

Defaults: `--start-at auto`, `--stop-after export`, `--batch-size 5`.

### 2. Bounded Phase Spans

Run only specific phases of the workflow:

```powershell
# Crawl only
$env:PYTHONUTF8=1
uv run python main.py orchestrate --workspace books/<book-slug> --start-at crawl --stop-after crawl

# Translate only
$env:PYTHONUTF8=1
uv run python main.py orchestrate --workspace books/<book-slug> --start-at translate --stop-after translate

# QA audit only
$env:PYTHONUTF8=1
uv run python main.py orchestrate --workspace books/<book-slug> --start-at qa --stop-after qa

# Export ebooks only
$env:PYTHONUTF8=1
uv run python main.py orchestrate --workspace books/<book-slug> --start-at export --stop-after export

# Translate through QA
$env:PYTHONUTF8=1
uv run python main.py orchestrate --workspace books/<book-slug> --start-at translate --stop-after qa
```

Valid phases in order: `crawl` -> `translate` -> `qa` -> `export`.

### 3. Resuming and Approval Decisions

When a run pauses for manual review (crawl or QA approval with warnings), it exits with code 2:

```powershell
# Inspect the pending review report
# (e.g. reports/crawl.yaml or reports/qa-report.yaml)

# Resume with approval
$env:PYTHONUTF8=1
uv run python main.py orchestrate --workspace books/<book-slug> --resume --decision approve

# Resume with rejection (halts run as blocked)
$env:PYTHONUTF8=1
uv run python main.py orchestrate --workspace books/<book-slug> --resume --decision reject

# Resume an interrupted translation batch without decision
$env:PYTHONUTF8=1
uv run python main.py orchestrate --workspace books/<book-slug> --resume
```

### 4. Tuning Models and Timeouts

```powershell
$env:PYTHONUTF8=1
uv run python main.py orchestrate --workspace books/<book-slug> `
  --start-at translate --stop-after translate `
  --batch-size 5 `
  --chapter-timeout 1800 `
  --agent-timeout 1800 `
  --formats epub,azw3 `
  --agy-model gemini-3.8-flash-high `
  --agy-translation-model gemini-3.8-flash-high `
  --auto-approve
```

- `--batch-size`: Number of chapters between graph checkpoints (default 5).
- `--chapter-timeout`: Wall-clock timeout in seconds per chapter translation process (default 1800).
- `--agy-model`: Default model slug for agent invocations.
- `--agy-translation-model`: Override model slug for chapter translation only.
- `--auto-approve`: Automatically approve crawl/QA gates with zero findings (refuses warnings).
- `--allow-harness-permission-bypass`: Explicit opt-in flag to bypass harness interactive prompts.

## Status and Exit Codes

| Exit Code | Status | Meaning |
| --- | --- | --- |
| 0 | `completed` | Requested phase span completed successfully. |
| 2 | `paused` | Manual review / approval required. Inspect report and resume with `--decision`. |
| 3 | `blocked` | Missing prerequisite gate, chapter gap, or unrecoverable error. Fix prerequisite before rerunning. |
| 1 | `error` | Unexpected runtime error. |

## Context Protection & Guardrails

- **Never read raw Chinese or full translation chapters into your Main Agent session.** Trust the compact CLI output and report files (`reports/runs/<run_id>/run_summary.json`).
- **Never use external LLM APIs.** All translations are performed by native child processes managed by the orchestrator.
- When Cowork runs on Linux, execute with:
  ```bash
  UV_CACHE_DIR=/tmp/uv-cache uv run --isolated --python 3.13 main.py orchestrate --workspace books/<book-slug>
  ```
