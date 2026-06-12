<!-- GENERATED from .harness/source by tools/sync_harness_adapters.py. Do not edit directly. -->

# Dich Truyen Agent - Shared Harness Orchestration Guide

This shared guide defines the agent-native orchestration workflow for translating Chinese novels into Vietnamese across supported harnesses.

## Workspace Lifecycle

The novel workspace evolves through deterministic gates. Downstream phases are blocked until preceding gates pass:

1. Initialize the workspace with `init-book`.
2. Crawl raw chapters with the harness-prefixed crawl skill.
3. Approve crawl evidence with `approve-crawl`.
4. Translate chapters sequentially with the harness-prefixed translate skill.
5. Run QA with the harness-prefixed check skill.
6. Approve QA evidence with `approve-qa`.
7. Export ebooks with the harness-prefixed export skill.

Verify gates with:
```powershell
$env:PYTHONUTF8=1
uv run python main.py check-gate --workspace books/<book-slug> --type <crawl-approved|qa-approved>
```

## Setup And Initialization

Initialize a clean book directory and build schemas with:
```powershell
$env:PYTHONUTF8=1
uv run python main.py init-book --slug <book-slug> --title "<title>" --source-url "<source-url>" [--author "<author>"]
```

When retrieving metadata from source sites, prefer terminal-driven HTTP requests with browser-like headers and explicit source encoding such as `gbk` or `utf-8`.

## Token & Context Protection

Never read raw source Chinese files or completed Vietnamese chapters into your own Main Agent session. Reading raw files quickly overwhelms the context window.

For large books, delegate the translation loop to a Coordinator Subagent that handles compact batches. The default batch size is 5 chapters and can be customized with `DICH_TRUYEN_TRANSLATION_BATCH_SIZE` in the project `.env` file. The Coordinator must spawn specialized Translator Subagents for individual chapter translation tasks. The Translator Subagent is the only worker that performs file-level raw chapter reading.

For 1000+ chapter books, full automation is allowed only through fresh compact batches. The Main Agent must re-query CLI state after each batch and must not accumulate promoted chapter arrays, raw text, completed translation text, or verbose per-chapter logs in its own context.

## Sequential Order & Context Handoff

Chapters must be translated strictly in order. Chapter `N` must use the completed Vietnamese output of Chapter `N-1` as narrative context to preserve pronoun continuity. If a gap or preceding missing chapter is discovered, stop execution and report it to the user.

## Failure Handling & Resumption

Translation retries default to 3 attempts with polite backoffs. Exhausted retries must halt the workflow immediately. Keep the workspace clean up to the last promoted chapter so that the run can resume later.

## External LLM API Guardrail

Never use an External LLM API, endpoint, SDK import, API key, Python script, curl request, or other external tool to perform translation. Use only the native harness translator subagent.

## Environment & Console Compatibility

Always run CLI commands with `PYTHONUTF8=1` to prevent Windows encoding errors:
```powershell
$env:PYTHONUTF8=1
uv run python main.py <command>
```

When running tests or tools in the sandbox, configure the uv cache:
```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
```

## Harness Capability Matrix

### Antigravity Panel

- Skills use the `ag-` prefix, including `ag-crawl-book`, `ag-translate-book`, `ag-check-translation`, and `ag-export-book`.
- Use `run_command` for CLI commands.
- Use `view_file` for bounded file inspection.
- Use `invoke_subagent` to delegate coordinator, translator, and metadata translation work.

### Claude Code Panel

- Skills use the `cc-` prefix, including `cc-crawl-book`, `cc-translate-book`, `cc-check-translation`, and `cc-export-book`.
- Use `Bash` for CLI commands.
- Use `Read` for bounded file inspection.
- Use `Agent` and `Workflow` for coordinator and translator delegation.

### OpenCode Panel

- Skills use the `oc-` prefix, including `oc-crawl-book`, `oc-translate-book`, `oc-check-translation`, and `oc-export-book`.
- Use `bash` for CLI commands.
- Use `read` for bounded file inspection.
- Use `task` for subagent delegation.
- Keep external LLM guardrails aligned with `opencode.json`.

### Codex Panel

- Skills use the `codex-` prefix, including `codex-crawl-book`, `codex-translate-book`, `codex-check-translation`, and `codex-export-book`.
- Use `shell_command` for CLI commands.
- Use `spawn_agent` for native Codex subagent delegation.
