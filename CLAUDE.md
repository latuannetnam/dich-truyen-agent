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

### Genre Profile Selection

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
4. Then run `init-book` with the confirmed `--style`:

```powershell
$env:PYTHONUTF8=1
uv run python main.py init-book --slug <book-slug> --title "<title>" --source-url "<source-url>" --style mat_the
```

`--style` is optional; it defaults to `general` if omitted. Do **not** omit it for genre-specific novels — use the table above to pick the right profile. Applying `tien_hiep` to a modern novel produces archaic phrasing in contemporary scenes.

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

## Claude Code Capability Panel

### Claude Code Panel

- Skills use the `cc-` prefix, including `cc-crawl-book`, `cc-translate-book`, `cc-check-translation`, and `cc-export-book`.
- Use `Bash` for CLI commands.
- Use `Read` for bounded file inspection.
- Use `Agent` and `Workflow` for coordinator and translator delegation.

### Claude Cowork Panel

- Claude Cowork is **built on Claude Code** and reads the same `.claude/` plugin adapters. Run the Claude Code pipeline skills directly: `cc-crawl-book`, `cc-translate-book`, `cc-check-translation`, and `cc-export-book`. There is no separate `cw-*` adapter set.
- **CLI form under Cowork's Linux sandbox.** The committed `.venv` is a Windows virtualenv and is unusable in Cowork's Linux sandbox. Run every CLI command in an isolated, ephemeral environment: `UV_CACHE_DIR=/tmp/uv-cache uv run --isolated --python 3.13 main.py <command>`. The Windows `$env:PYTHONUTF8=1; uv run python main.py ...` form applies only when running on Windows.
- **Custom subagents are not dispatchable in Cowork.** Cowork's `Agent` tool exposes only built-in agents, so the `cc_coordinator` / `cc_translator` / `cc_metadata_translator` dispatch that Claude Code uses does **not** work here. Use the **Cowork Fallback Dispatch** documented in the `cc-translate-book` skill: the Main Agent runs the compact per-chapter loop itself (no Coordinator tier) and dispatches a built-in **general agent** for each chapter, instructing it to read and follow `.claude/agents/cc_translator.md` against the `next-translation-work-item` paths. Metadata translation dispatches a general agent that follows `.claude/agents/cc_metadata_translator.md`.
- **Token protection still holds.** The Main Agent handles only CLI JSON and dispatch; the dispatched general worker is the only worker that reads raw chapter files, in its own isolated context. Never read raw Chinese or completed Vietnamese chapters into the Main Agent session.
- **Cowork hooks do not fire.** The `check_external_llm.py` guardrail hook is inert under Cowork, so the external-LLM prohibition is enforced at **instruction level** inside the skills and agents. Never use an external LLM API to translate, regardless of hook state.
- **Verify the general-agent dispatch on a small book first.** Before running large books, confirm the built-in general worker correctly reads and applies the `cc_translator` instructions in your Cowork build.
