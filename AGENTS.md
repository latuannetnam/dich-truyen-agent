<!-- GENERATED from .harness/source by tools/sync_harness_adapters.py. Do not edit directly. -->

# Dich Truyen Agent - Shared Harness Orchestration Guide

This shared guide defines the agent-native orchestration workflow and development procedures for translating Chinese novels into Vietnamese across supported harnesses.

## Operations

### Workspace Lifecycle

The novel workspace evolves through deterministic gates managed by the central orchestrator CLI:

1. Initialize the workspace with `init-book`.
2. Orchestrate pipeline phases via `orchestrate --workspace books/<book-slug> [--start-at <phase>] [--stop-after <phase>]`.
   - **Crawl:** Discovers the chapter catalog and downloads raw chapters.
   - **Translate:** Translates chapters strictly in order with isolated native workers.
   - **QA:** Scans for residue, length anomalies, and glossary conflicts.
   - **Export:** Validates compliance and compiles canonical EPUB and derivatives.

Downstream phases are blocked until preceding gates pass:
```powershell
$env:PYTHONUTF8=1
uv run python main.py check-gate --workspace books/<book-slug> --type <crawl-approved|qa-approved>
```

### Setup And Initialization

Initialize a clean book directory:
```powershell
$env:PYTHONUTF8=1
uv run python main.py init-book --slug <book-slug> --title "<title>" --source-url "<source-url>" [--author "<author>"]
```

When retrieving metadata from source sites, prefer terminal-driven HTTP requests with browser-like headers and explicit source encoding such as `gbk` or `utf-8`.

#### Genre Profile Selection

Before running `init-book`, infer the book's genre from its title and source metadata, then select the most appropriate style profile:

| Genre | `--style` flag | When to use |
| --- | --- | --- |
| Apocalypse / survival (mạt thế) | `mat_the` | Zombie, doomsday, post-collapse survival novels |
| Modern urban | `do_thi` | Contemporary city life, office romance, modern drama |
| Xianxia / cultivation | `tien_hiep` | Martial arts, immortal cultivation, wuxia |
| Anything else / unsure | `general` | Genre not listed above, or unclear — default if omitted |

**Recommendation flow:**

1. Read the book title and any available synopsis or chapter 1 excerpt.
2. Recommend a `--style` value to the user and explain why.
3. Wait for the user to confirm or override.
4. Run `init-book` with the confirmed `--style`:
   ```powershell
   $env:PYTHONUTF8=1
   uv run python main.py init-book --slug <book-slug> --title "<title>" --source-url "<source-url>" --style mat_the
   ```

Do not omit `--style` for genre-specific novels.

### Running the Orchestrator

The single `orchestrate` CLI command executes and supervises the lifecycle:

```powershell
# Full remaining pipeline (default: start at auto, stop after export)
$env:PYTHONUTF8=1
uv run python main.py orchestrate --workspace books/<book-slug>

# Explicit phase bounds
uv run python main.py orchestrate --workspace books/<book-slug> --start-at crawl --stop-after crawl
uv run python main.py orchestrate --workspace books/<book-slug> --start-at translate --stop-after translate
uv run python main.py orchestrate --workspace books/<book-slug> --start-at qa --stop-after qa
uv run python main.py orchestrate --workspace books/<book-slug> --start-at export --stop-after export
```

### Gate Review and Human Approval Flow

When a crawl or QA report contains warnings or requires human review, the orchestrator pauses and exits with code 2:

1. Inspect the review report with bounded file reading:
   - Crawl report: `books/<book-slug>/reports/crawl.yaml`
   - QA report: `books/<book-slug>/reports/qa-report.yaml`
2. Submit the operator decision:
   ```powershell
   # Approve and proceed
   $env:PYTHONUTF8=1
   uv run python main.py orchestrate --workspace books/<book-slug> --resume --decision approve

   # Reject (halts run as blocked)
   $env:PYTHONUTF8=1
   uv run python main.py orchestrate --workspace books/<book-slug> --resume --decision reject
   ```

### Model Selection Flags

- `--agy-model <slug>`: Sets the default model for all agent invocations.
- `--agy-translation-model <slug>`: Overrides model selection for chapter translation only.

Model slugs are preflight-checked on the target `agy` installation before launch and pinned on resume.

### Status and Exit Codes

| Exit Code | Status | Meaning |
| --- | --- | --- |
| 0 | `completed` | Requested phase span completed successfully. |
| 2 | `paused` | Manual review / approval required. Inspect report and resume with `--decision`. |
| 3 | `blocked` | Prerequisite missing, gap detected, or unrecoverable error. Address blocker before rerunning. |
| 1 | `error` | Unexpected runtime error. |

### Token & Context Protection

Never read raw source Chinese files or completed Vietnamese chapters into your own Main Agent session. Reading raw files quickly overwhelms the context window.

The orchestrator dispatches fresh, isolated Antigravity worker processes for individual chapter translation tasks. The Translator Subagent is the only worker that performs file-level raw chapter reading. Graph state and CLI summaries hold only paths, hashes, counts, and bounded diagnostics.

### Sequential Order & Context Handoff

Chapters must be translated strictly in order. Chapter `N` must use the completed Vietnamese output of Chapter `N-1` as narrative context to preserve pronoun continuity. If a gap or preceding missing chapter is discovered, stop execution and report it to the user.

### External LLM API Guardrail

Never use an External LLM API, endpoint, SDK import, API key, Python script, curl request, or other external tool to perform translation. Use only the native harness translator subagent.

### Environment & Console Compatibility

Always run CLI commands with `PYTHONUTF8=1` on Windows:
```powershell
$env:PYTHONUTF8=1
uv run python main.py <command>
```

When running in sandbox environments, configure the uv cache:
```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
```

---

## Development

### Architecture and Ownership

- Detailed design: `docs/superpowers/specs/2026-09-25-orchestrator-langgraph-design.md`.
- **Deterministic domain operations** (`src/dich_truyen_agent/`): Own crawler, verification, atomic chapter promotion, QA scanning, approval writes, and ebook export.
- **Orchestrator** (`src/dich_truyen_agent/orchestrator/`): Coordinates phase routing, process supervision, attempt journals, SQLite checkpoints (`reports/runs/<run_id>/checkpoint.sqlite`), and workspace locking.
- **Harness runner** (`orchestrator/runners/agy.py`): Supervises Antigravity CLI processes; never decides domain success independently.

### Running Quality and Test Suites

Run quality checks with `PYTHONUTF8=1` and workspace-local `UV_CACHE_DIR`:
```powershell
$env:PYTHONUTF8=1
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run pytest -q
uv run ruff check src tests main.py tools/sync_harness_adapters.py
uv run ruff format --check src tests main.py tools/sync_harness_adapters.py
uv run python tools/sync_harness_adapters.py --check
```

## Harness Capability Matrix

### Antigravity Panel

- Skills use the `ag-` prefix: `ag-orchestrate-book`, `ag-crawl-book`, `ag-translate-book`, `ag-check-translation`, and `ag-export-book`.
- Use `run_command` for CLI commands.
- Use `view_file` for bounded file inspection.
- Antigravity CLI serves as the initial agent execution backend for the orchestrator (`ag_translator` and `ag_metadata_translator`).

### Claude Code Panel

- Skills use the `cc-` prefix: `cc-orchestrate-book`, `cc-crawl-book`, `cc-translate-book`, `cc-check-translation`, and `cc-export-book`.
- Use `Bash` for CLI commands.
- Use `Read` for bounded file inspection.
- Operating skills invoke the unified orchestrator CLI; no coordinator or translator subagent dispatch needed.

### OpenCode Panel

- Skills use the `oc-` prefix: `oc-orchestrate-book`, `oc-crawl-book`, `oc-translate-book`, `oc-check-translation`, and `oc-export-book`.
- Use `bash` for CLI commands.
- Use `read` for bounded file inspection.
- Keep external LLM guardrails aligned with `opencode.json`.

### Codex Panel

- Skills use the `codex-` prefix: `codex-orchestrate-book`, `codex-crawl-book`, `codex-translate-book`, `codex-check-translation`, and `codex-export-book`.
- Use `shell_command` for CLI commands.

### Claude Cowork Panel

- Claude Cowork is **built on Claude Code** and reads the same `.claude/` plugin adapters. Run the Claude Code pipeline skills directly: `cc-orchestrate-book`, `cc-crawl-book`, `cc-translate-book`, `cc-check-translation`, and `cc-export-book`. There is no separate `cw-*` adapter set.
- **CLI form under Cowork's Linux sandbox:** The committed `.venv` is a Windows virtualenv and is unusable in Cowork's Linux sandbox. Run every CLI command in an isolated, ephemeral environment:
  ```bash
  UV_CACHE_DIR=/tmp/uv-cache uv run --isolated --python 3.13 main.py <command>
  ```
- **Token protection still holds:** The Main Agent handles only CLI JSON and dispatch. Never read raw Chinese or completed Vietnamese chapters into the Main Agent session.
- **Cowork hooks do not fire:** The `check_external_llm.py` guardrail hook is inert under Cowork, so the external-LLM prohibition is enforced at **instruction level** inside the skills. Never use an external LLM API to translate.
