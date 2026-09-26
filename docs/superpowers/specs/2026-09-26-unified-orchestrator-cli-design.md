# Unified Orchestrator CLI Design (End-to-End Single-Command & Interactive UX)

- **Date:** 2026-09-26
- **Status:** Approved, ready for implementation planning
- **Context:** The pipeline previously required multiple separate commands (`init-book`, manual catalog editing for partial scopes, `orchestrate`, and repeated `--resume --decision approve` commands upon gate pauses). This design unifies the CLI experience into a single command capable of running the entire pipeline from scratch, interacting on the terminal or running unattended with `--yes`, while retaining full checkpoint-based resume capabilities at any step.

---

## 1. Objectives and Scope

1. **Single-Command End-to-End Execution:**
   Allow users to run a novel translation pipeline from raw URL to exported ebook (PDF, EPUB) using a single command:
   ```powershell
   uv run python main.py orchestrate --url "<source-url>" --slug "<book-slug>" --style <style> --limit <N> --formats pdf,epub --yes
   ```
2. **Auto-Initialization (Auto-Init):**
   If `--workspace` does not exist yet (or `--slug` is given with `--url`), `orchestrate` automatically invokes workspace initialization (`initialize_workspace`) before entering the LangGraph orchestrator graph.
3. **Scoped Chapter Crawling (`--limit` & `--chapter-range`):**
   Support `--limit <N>` and `--chapter-range <start>-<end>` at both crawl level and orchestrator level:
   - Slices the catalog to exactly the requested chapters during discovery/crawling.
   - Ensures `chapters.yaml` and `state.yaml` only hold the scoped chapters.
   - Evaluates `ApprovalScope.FULL` naturally without manual file editing or partial approval rejections.
4. **Console Interactive Approval & Unattended Mode (`--yes`):**
   - In unattended mode (`--yes` / `-y` / `--auto-approve`): Automatically approves clean gates (or gates with warnings only, e.g. length ratio) without stopping.
   - In interactive mode (when running in terminal with `sys.stdin.isatty()` and without `--yes`): Instead of exiting with code 2, prints a bounded report summary and prompts:
     `[?] Phê duyệt báo cáo để tiếp tục sang bước tiếp theo? [Y/n]: `
     If user confirms, continues execution immediately in the same process session.
   - In headless/script mode: Retains exit code 2 pause behavior for automated harnesses / supervisor agents.
5. **Resume & Phase Bounds Intact:**
   Retains `--resume`, `--start-at <phase>`, and `--stop-after <phase>` so any interrupted run can resume or run individual phases independently.
6. **Live Validation Acceptance Test:**
   Delete `books/tien-phu-truong-sinh`, run:
   ```powershell
   uv run python main.py orchestrate --url "https://www.piaotia.com/html/15/15305/" --slug tien-phu-truong-sinh --style tien_hiep --limit 3 --formats pdf,epub --yes
   ```
   Verify 3 chapters are crawled, translated, QA-scanned, and exported to PDF and EPUB with 0 errors.

---

## 2. Architecture & Ownership

| Component | Responsibility |
| --- | --- |
| `cli.py` (`orchestrate` parser & supervisor loop) | Parses unified flags (`--url`, `--slug`, `--style`, `--limit`, `--chapter-range`, `--yes`). Handles auto-init if workspace is absent. Runs execution loop with interactive `[Y/n]` prompt or auto-approval. |
| `crawler.py` & `crawl_batch.py` | Accepts `limit` and `chapter_range` to slice discovered chapters before fetching raw text and registering catalog. |
| `orchestrator/orchestrator.py` & `graph.py` | Receives `limit` in `OrchestratorConfig`. Coordinates LangGraph state transitions and checkpoints. |
| `export.py` & `runners/agy.py` | Auto-detects local tools (`epubcheck.jar`, Calibre `ebook-convert`, `agy.exe`). |

---

## 3. Detailed Component Design

### 3.1 CLI Arguments Extension (`src/dich_truyen_agent/cli.py`)

Extend `orchestrate` parser:
```python
orch.add_argument("--url", type=str, default=None, help="Source novel index URL for auto-initialization")
orch.add_argument("--slug", type=str, default=None, help="Book slug (used with --url to create books/<slug>)")
orch.add_argument("--title", type=str, default=None, help="Book title (optional, crawler extracts if omitted)")
orch.add_argument("--author", type=str, default=None, help="Book author (optional)")
orch.add_argument("--style", type=str, default="general", help="Translation style profile (tien_hiep, mat_the, etc.)")
orch.add_argument("--limit", type=int, default=None, help="Limit number of chapters to crawl and translate (e.g. 10)")
orch.add_argument("--chapter-range", type=str, default=None, help="Range of chapters to crawl and translate (e.g. 1-10)")
orch.add_argument("-y", "--yes", action="store_true", help="Automatically approve gates with warnings without prompting")
```
Make `--workspace` optional if `--slug` or `--url` is provided (defaults to `books/<slug>`).

### 3.2 Auto-Init Flow
Inside `run_command` for `orchestrate`:
```python
if workspace_root is None or not workspace_root.exists():
    if not args.url:
        return OperationResult(status=OperationStatus.ERROR, reason="Workspace does not exist. Please provide --url to initialize.")
    slug = args.slug or sanitize_slug(args.title or "novel")
    workspace_root = workspace_paths(PROJECT_ROOT / "books", slug).root
    style = load_selected_style(PROJECT_ROOT, args.style)
    metadata = BookMetadata(book_slug=slug, source_url=args.url, title=args.title, author=args.author)
    init_res = initialize_workspace(PROJECT_ROOT / "books", metadata, ChapterCatalog(), style)
    if init_res.status != OperationStatus.OK:
        return init_res
```

### 3.3 Scoped Chapter Crawling (`crawler.py` & `crawl_batch.py`)
In `crawl_book`:
- If `limit` is set: `catalog.chapters = catalog.chapters[:limit]`
- If `chapter_range` is set (e.g. `start, end`): `catalog.chapters = [c for c in catalog.chapters if start <= c.chapter_id <= end]`
- Then re-index IDs sequentially if needed, download raw chapters for the scoped list, write `chapters.yaml` and `state.yaml`.
- Bounded catalog ensures `reports/crawl.yaml` reflects 100% completion of the requested scope (`FULL`).

### 3.4 Interactive & Auto-Approval Supervisor Loop
In `cli.py`:
```python
outcome = orchestrator.run(config)
while outcome.status == "paused":
    # 1. Unattended mode (--yes or --auto-approve)
    if (args.yes or args.auto_approve) and outcome.error_count == 0:
        print(f"\n[Auto-Approve] Approving gate {outcome.pending_approval} ({outcome.warning_count} warnings, 0 errors)...")
        outcome = orchestrator.resume_run(workspace_root, run_id=outcome.run_id, decision="approve")
        continue

    # 2. Interactive Terminal mode
    if sys.stdin.isatty():
        print_gate_summary(outcome)
        choice = input(f"[?] Phe duyet de tiep tuc sang buoc tiep theo? [Y/n]: ").strip().lower()
        if choice in ("", "y", "yes"):
            outcome = orchestrator.resume_run(workspace_root, run_id=outcome.run_id, decision="approve")
            continue
        else:
            outcome = orchestrator.resume_run(workspace_root, run_id=outcome.run_id, decision="reject")
            break

    # 3. Headless / Agent mode: break and exit with code 2
    break
```

---

## 4. Error Handling & Invariants

1. **Context Protection:** Never read raw Chinese or full Vietnamese chapter contents into CLI console or main agent context. Print only chapter counts, ratios, titles, and report paths.
2. **Deterministic Blocking on Errors:** If `outcome.error_count > 0` (e.g. missing chapters, download failures), `--yes` does NOT auto-approve; it halts with exit code 3 (blocked).
3. **Workspace Locking:** Workspace lock remains held throughout the execution and resume loop.
4. **SQLite Checkpoints:** Every batch, chapter promotion, and gate approval commits to SQLite checkpointing.

---

## 5. Verification & Acceptance Criteria

1. **Unit & Integration Tests:**
   - Test auto-init via `orchestrate --url ... --slug ...`.
   - Test crawl scoping with `--limit 2` producing exactly 2 chapters.
   - Test interactive prompt simulation (mocking stdin input `y` and `n`).
   - Test `--yes` auto-approval loop continuing to `completed`.
   - All 544 existing unit tests pass without regressions.
2. **Live Acceptance Test:**
   - Remove existing `books/tien-phu-truong-sinh`.
   - Execute:
     ```powershell
     $env:PYTHONUTF8=1; uv run python main.py orchestrate --url "https://www.piaotia.com/html/15/15305/" --slug tien-phu-truong-sinh --style tien_hiep --limit 3 --formats pdf,epub --yes
     ```
   - Assert exit code 0.
   - Assert `exports/tien-phu-truong-sinh.pdf` and `exports/tien-phu-truong-sinh.epub` exist and size > 0.
   - Assert `translations/0001-1.txt`, `0002-2.txt`, `0003-3.txt` exist.

---

## 6. Documentation & Harness Adapter Synchronization

1. **Source Guide & Documentation Updates:**
   - Update `.harness/source/guides/shared-main-agent.md` with the new unified single-command workflow, auto-init, `--limit`, and `--yes` / interactive approval capabilities.
   - Update `README.md` and `ARCHITECTURE.md` to reflect the unified end-to-end command and updated orchestrator lifecycle.
2. **Adapter Synchronization (`tools/sync_harness_adapters.py`):**
   - Run `uv run python tools/sync_harness_adapters.py` to regenerate all harness guides and skills:
     - Root `AGENTS.md` and `CLAUDE.md`.
     - Antigravity skills (`ag-orchestrate-book`, etc.).
     - Claude Code skills (`cc-orchestrate-book`, etc.).
     - OpenCode skills (`oc-orchestrate-book`, etc.).
     - Codex skills (`codex-orchestrate-book`, etc.).
   - Verify `uv run python tools/sync_harness_adapters.py --check` passes cleanly without drift.

