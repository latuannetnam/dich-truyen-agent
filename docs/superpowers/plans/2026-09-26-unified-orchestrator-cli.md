# Unified Orchestrator CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run a new book from URL through export in one command, with a provenance-backed prefix scope and safe terminal or unattended gate decisions.

**Architecture:** Extend the existing `crawl_batch.crawl_book` and workspace gate operations, then connect them through `BookOrchestrator.start`/`resume` and `cli.run_orchestrate`. The LangGraph approval interrupt stays authoritative. A scoped workspace records the complete source catalog and hashes that record into both gates; legacy full-book workspaces retain their current contract.

**Tech stack:** Python 3.13, Pydantic, LangGraph, SQLite, pytest, Ruff. The live Antigravity/site smoke check is optional and separate from automated tests.

**Design:** [2026-09-26-unified-orchestrator-cli-design.md](../specs/2026-09-26-unified-orchestrator-cli-design.md)

## Current interfaces to preserve

- `src/dich_truyen_agent/cli.py`: `orchestrate` is handled by `run_orchestrate()` and `main()`, outside `run_command()`; `--workspace` is currently required.
- `src/dich_truyen_agent/orchestrator/orchestrator.py`: public methods are `BookOrchestrator.start(config)` and `.resume(workspace, decision=...)`. `WorkspaceLock` lives in this file. `GraphRunner.run()` is internal.
- `src/dich_truyen_agent/crawl_batch.py`: async `crawl_book(...)` discovers, registers, and downloads; `crawler.py` supplies `discover_catalog`, `validate_discovered_catalog`, and `to_chapter_catalog`. `crawl-book --max-chapters` currently limits downloads only.
- `CrawlReport` has direct `discovered_count`, `selected_count`, `scope`, `blockers`, and `warnings` fields; it has no `summary` or `CrawlReportSummary`. `approve_checkpoint` requires `report_path` and `evidence_paths`. The graph's `_compute_*_evidence_hashes` live in `orchestrator/graph.py`.
- Use the real fixtures and `MockRunner` patterns in `tests/orchestrator_support.py`, `tests/test_orchestrator_approval.py`, and `tests/test_orchestrator_lifecycle.py`. Do not invent a `TranslationStyle.rules` field or a `RunOutcome.error_count` field.

Set `$env:PYTHONUTF8=1` and `$env:UV_CACHE_DIR="$PWD\.uv-cache"` before Windows `uv` commands in every task. Keep raw Chinese and completed Vietnamese chapters out of main-agent output. No new `--chapter-range` flag is part of this plan.

## Task 1: Model and validate frozen source scope

**Files:** `src/dich_truyen_agent/models.py`, `src/dich_truyen_agent/paths.py`, new `src/dich_truyen_agent/scope.py`, new `tests/test_source_scope.py`.

- [ ] Add a failing pure-domain test for `build_source_scope(discovered: list[DiscoveredChapter], source_url: str, limit: int | None)` using five real `DiscoveredChapter` objects. Assert a limit of 3 returns source count 5, selected IDs `[1, 2, 3]`, the first three URLs, and a digest of **all five** ordered source entries. Assert full mode selects all five. Parameterize zero, negative, greater-than-count, empty discovery, duplicate URL, and numeric gap as rejected inputs. Assert a changed title, URL, or order changes the digest.
- [ ] Run `uv run pytest -q tests/test_source_scope.py`; expect red because `dich_truyen_agent.scope` does not exist.
- [ ] Define a versioned `SourceScopeRecord` in `models.py` with source URL, full ordered entries (`position`, `source_id`, URL, title, parsed ordinal), source digest/count, mode (`full|prefix`), requested limit, selected ordered IDs/URLs, and selected count. Validate positive contiguous source positions, nonempty/full selection, prefix identity, count/digest consistency, and reject extra fields. Use `DiscoveredChapter` or a focused persisted entry model with the same field names; choose one and use it consistently in the tests and serializer.
- [ ] Add `WorkspacePaths.source_scope` (`reports/source-scope.yaml`). In `scope.py`, implement deterministic digest calculation from canonical serialized entry fields, `build_source_scope`, atomic save/load, and `validate_scope_catalog(record, catalog)`. The latter must compare source URL, selection order, selected IDs/URLs/titles, and derived digest; it must re-run the existing catalog validator on the **full** recorded source list. Return a bounded reason or typed failure without chapter bodies.
- [ ] Add a `BookMetadata.scope_managed: bool = False` marker. Only new unified workspaces set it true. It distinguishes a missing scope file from a legacy workspace; metadata translation must preserve it.
- [ ] Run the targeted test until green and `uv run ruff check src/dich_truyen_agent/scope.py src/dich_truyen_agent/models.py src/dich_truyen_agent/paths.py tests/test_source_scope.py`. Commit only these files.

## Task 2: Integrate prefix selection into the real crawl path

**Files:** `src/dich_truyen_agent/crawl_batch.py`, `src/dich_truyen_agent/crawler.py` only if a shared discovery helper is needed, `src/dich_truyen_agent/crawl_reports.py`, `src/dich_truyen_agent/models.py`, `src/dich_truyen_agent/cli.py` (`crawl-book` parser/dispatch only), `src/dich_truyen_agent/orchestrator/workspace_ops.py`, new `tests/test_scoped_crawl.py`.

- [ ] Start with a fixture-based failing test around async `crawl_batch.crawl_book`, replacing its HTTP crawler and browser renderer as current crawl tests do. Discover five chapters with valid ordinals, request scope limit 3, then assert exactly three catalog/state/raw records, a five-entry scope record, and `CrawlReport` direct fields `discovered_count == selected_count == completed_count == 3`, `source_discovered_count == 5`, `scope == FULL`, and `scope_summary == "prefix 3 of 5"`. Assert a later retry skips valid raw files and a changed source catalog blocks without replacing scope/catalog/state.
- [ ] Run `uv run pytest -q tests/test_scoped_crawl.py`; expect red on missing scoped parameter/report fields.
- [ ] Add `scope_limit: int | None = None` to `crawl_batch.crawl_book`, separate from existing `max_chapters: int = 0`. In its empty-catalog discovery branch, validate the **whole** `discover_catalog` result before selection, build and atomically persist source scope, then create the selected `ChapterCatalog` and matching `BookState`. If a crash left a valid scope record with an empty catalog, rebuild only its already selected catalog/state; if it left a nonempty catalog with missing or mismatched scope, block for operator repair. For an existing nonempty catalog with `scope_managed`, load and validate its scope before download; never reselect or reset translated state. If a fresh discovery is made during retry, compare the full digest and block `catalog-changed` before writes. Keep `--max-chapters` behavior unchanged for the legacy command.
- [ ] Add `--scope-limit` as an internal `crawl-book` flag (positive integer; incompatible with nonzero `--max-chapters`) and pass it from `WorkspaceOps.run_crawl`; do not expose it as `--limit` on `crawl-book`. Make `graph.py` pass the pinned config's scope limit through `WorkspaceOps.run_crawl`.
- [ ] Extend `CrawlReport` with backward-compatible optional `source_discovered_count` and `scope_summary`. `build_crawl_report` loads/validates scope when `book.yaml` is marked scope-managed, sets existing discovered/selected counts to the **selected workspace catalog**, rechecks full-source blockers from the scope record, and blocks if scope/catalog/state/raw disagree. Keep legacy report fields and `max_chapters` interpretation intact. Avoid a fabricated `report.summary` object.
- [ ] Add tests for incomplete selected raw, source gap outside the selected prefix, duplicate URL, empty/too-short discovery, `--limit > source count`, scope digest mismatch, interrupted scope/catalog persistence, partial `--max-chapters`, and unchanged legacy crawl. Run `uv run pytest -q tests/test_scoped_crawl.py tests/test_crawl_batch.py tests/test_crawl_reports.py`; commit focused files.

## Task 3: Bind scope to approval and paused decisions

**Files:** `src/dich_truyen_agent/checkpoints.py`, `src/dich_truyen_agent/orchestrator/graph.py`, new `tests/test_scoped_gates.py`.

- [ ] Create a failing test with a real nonempty selected catalog, raw files, `CrawlReport`, and scope record. Call `approve_full_crawl`, then `check_orchestrator_gate(CRAWL_APPROVED)`. Assert the approval's `evidence_hashes` contains `reports/source-scope.yaml`; after changing or deleting that file, the gate blocks. Repeat for `approve_current_qa` with completed translations and the QA gate. A test with `scope_managed=True` and missing record must block; a legacy fixture with no marker/record must still pass its existing valid gate. A QA warning manually approved with `allow_warnings=True` must record partial QA scope and still pass the current QA gate, while `auto_approve=True` pauses.
- [ ] Run `uv run pytest -q tests/test_scoped_gates.py`; expect red on missing scope evidence.
- [ ] In `approve_full_crawl`, append `reports/source-scope.yaml` to `evidence_paths` when scope-managed, after validating source scope, selected catalog, report counts, all selected raw hashes, and full-source blockers. In `approve_current_qa`, append the same path to its existing catalog/state/report/translation evidence. Do not change the public `approve_checkpoint` call shape. In strict `check_gate`, require the scope entry for marked workspaces and reject a missing/malformed scope file; preserve legacy checks.
- [ ] Add the scope hash to `graph.py`'s `_compute_crawl_evidence_hashes` and `_compute_qa_evidence_hashes` so an interrupted approval cannot accept changed scope. Reject rather than silently omit missing required evidence. Ensure a changed scope during pause blocks before approval and an old full-book gate cannot be reused after scope changes.
- [ ] Run `uv run pytest -q tests/test_scoped_gates.py tests/test_orchestrator_approval.py tests/test_checkpoints.py`; commit focused files.

## Task 4: Migrate all orchestrator entry paths to a stable external lock

**Files:** `src/dich_truyen_agent/orchestrator/orchestrator.py`, new `tests/test_orchestrator_external_lock.py`.

- [ ] Write a failing lock test asserting `_lock_path(books_root / slug)` resolves to `<books-root>/.orchestrator-locks/<slug>.lock` before the workspace exists, and `WorkspaceLock.release()` leaves the lock file in place. Test contention using two independent lock instances, including while the first run is paused and the CLI is about to call `.resume()`.
- [ ] Run `uv run pytest -q tests/test_orchestrator_external_lock.py`; expect red because the current path is workspace-local and `release()` unlinks it.
- [ ] Make `BookOrchestrator.start` and `.resume` acquire the same canonical external path; keep it stable after release. For an existing workspace with the old `reports/runs/.orchestrator.lock`, acquire that legacy lock **after** the external lock and hold both through each start/resume call, so a still-running old process prevents entry. Release in reverse order. Do not create a legacy lock for a new workspace. Validate slug/path with `workspace_paths` before deriving the lock path.
- [ ] Test simultaneous old and new entry paths, lock release on `completed`, `paused`, `blocked`, and exception, and absence of a partial workspace when pre-init validation fails. Run `uv run pytest -q tests/test_orchestrator_external_lock.py tests/test_orchestrator_lifecycle.py`; commit focused files.

## Task 5: Auto-init and pin the entire run policy on resume

**Files:** `src/dich_truyen_agent/orchestrator/models.py`, `src/dich_truyen_agent/orchestrator/orchestrator.py`, `src/dich_truyen_agent/orchestrator/graph.py`, `src/dich_truyen_agent/orchestrator/tracer.py`, `src/dich_truyen_agent/crawl_batch.py` if shared index discovery is factored there, new `tests/test_orchestrator_auto_init.py`, new `tests/test_orchestrator_policy_resume.py`.

- [ ] First write tests using valid UUID run IDs and existing `MockRunner`/workspace fixtures. Cover URL+slug+style+limit creating a workspace and entering crawl under one lock; supplied title with failed discovery creating an empty-catalog workspace that reaches profile repair; missing title with failed discovery leaving no initialized workspace; omitted title with successful discovery using the real extracted title; invalid style/limit/path blocking before network access. For a pause, inspect `run_summary.json`, resume the same run ID, and assert scope, formats, auto approval, crawl/translation/QA/export timeouts, batch size, retry budgets, model pins, and permission policy stay identical. Ensure replay does not duplicate initialization, approval, or promoted chapters.
- [ ] Run `uv run pytest -q tests/test_orchestrator_auto_init.py tests/test_orchestrator_policy_resume.py`; expect red on absent creation fields/policy pinning.
- [ ] Add creation fields (`source_url`, `book_slug`, optional title/author/style, `scope_limit`) to `OrchestratorConfig`, validating positive scope and valid URL/slug. Keep run IDs UUIDs. Add a serialized `run_policy` field to `RunSummary` for the effective `scope_limit`, `formats`, `auto_approve`, `allow_warnings`, `batch_size`, all timeout and retry fields, model slugs, and permission-bypass flag; keep phase span and run ID pinned as existing summary fields. Add a nullable `source_scope_digest` and `scope_summary` to the run summary, set when the scoped crawl binds its catalog. Write policy at run creation through `GraphRunner`/`ActivityTracer`, then reconstruct `OrchestratorConfig` from it in `BookOrchestrator.resume` and verify the saved digest against the current scope file. For old summaries without `run_policy`, preserve the legacy fallback. Reject new creation/model/phase options on `--resume` in the CLI.
- [ ] Factor `BookOrchestrator.start` into a public lock-acquiring wrapper and a private locked execution method. While holding the lock, validate target/source/style and discover the index via the same deterministic crawler/profile/browser helper used by `crawl_book` to establish a usable title. Initialize with that title and an **empty** `ChapterCatalog`, then enter graph crawl; the graph's scoped crawl performs authoritative full discovery and atomically binds the selected catalog/scope before approval. If initial discovery fails and an explicit title exists, use the same empty-catalog init and let the graph's existing profile-repair path discover/bind scope. If it fails without title, block before `initialize_workspace`. Never use slug/`"novel"` as a metadata title. On initialized retry, inspect source/style/scope and preserve existing files; a new limit cannot change a bound scope.
- [ ] Make `WorkspaceOps.run_crawl` and `graph.py` use the pinned `scope_limit`; for an already bound scope, use its selected catalog and avoid rediscovery unless a retry actually discovers again. Preserve phase-entry evidence checks and normal `--workspace` legacy runs. Run the two new test files plus `tests/test_orchestrator_lifecycle.py tests/test_orchestrator_phase_entry.py tests/test_orchestrator_matrix_resume.py`; commit focused files.

## Task 6: Wire CLI inputs and one-process approval UX

**Files:** `src/dich_truyen_agent/cli.py`, `tests/test_orchestrator_cli.py`, new `tests/test_unified_cli.py`.

- [ ] Add failing tests around **`run_orchestrate()` and `main()`**, not `run_command()`. Cover URL+slug+style/`--limit` path derivation, including an already existing derived workspace; mismatching `--workspace`/slug/URL/style; rejection of creation-only title/author on existing workspaces; existing full and legacy workspaces; `--resume` override rejection; invalid positive limit and missing style; `--json` never prompting; `-y`, `--yes`, and `--auto-approve` mapping to the same clean-only policy. Verify invalid combinations return `RunOutcome(status="blocked", exit_code=3)` before network/workspace writes.
- [ ] Add TTY tests using a paused `RunOutcome` with valid required fields (`run_id`, `selected_span`, `current_phase`, report path/hash): `y` calls `BookOrchestrator.resume(..., decision="approve")` with the same workspace/run; `n` rejects; Enter/EOF defers with exit 2; stdout or stdin non-TTY defers; `--json` and `--yes` defer without a prompt. Test a crawl warning and a QA warning under `--yes`; neither may call `.resume()`. Test two distinct gates and repeated same gate/hash stopping with a diagnostic. CLI must not read raw chapter files.
- [ ] Run `uv run pytest -q tests/test_unified_cli.py`; expect red on missing flags/prompt.
- [ ] Extend the `orchestrate` parser with `--url`, `--slug`, `--title`, `--author`, `--style`, `--limit`, and aliases `-y/--yes` for existing `--auto-approve`. Resolve paths with `workspace_paths` and compare existing persisted metadata/style. Preserve `--workspace`, phase bounds, model flags, `--formats`, and exit code behavior. Track whether options were explicitly supplied, so `--resume` rejects creation inputs and overrides to saved scope, formats, auto approval, timeouts, batch/retry settings, models, and phase span while accepting their parser defaults. Reject `--chapter-range` as unrecognized. Do not route this command through `run_command`.
- [ ] Let the graph auto approve clean gates. After `BookOrchestrator.start` or `.resume` returns `paused`, prompt only when both streams are TTYs and neither `--json` nor `--yes/--auto-approve` is set. Load the named typed report from the reported workspace-relative path, show bounded counts/warnings, scope, run ID and report hash, and submit only explicit `y` or `n` via `.resume`. Enter/EOF returns the paused outcome. Track `(run_id, pending_approval, approval_report_hash)` to stop a repeated interrupt. On completion, print the persisted `scope_summary` with the export paths, so a prefix export is not presented as the full source. Use `RunOutcome`, not `OperationResult`, throughout.
- [ ] Run `uv run pytest -q tests/test_unified_cli.py tests/test_orchestrator_cli.py tests/test_orchestrator_approval.py`; commit focused files.

## Task 7: Acceptance matrix, docs, and adapter sync

**Files:** `tests/test_scoped_crawl.py`, `tests/test_scoped_gates.py`, `tests/test_orchestrator_auto_init.py`, `tests/test_unified_cli.py`, `.harness/source/guides/shared-main-agent.md`, `README.md`, `ARCHITECTURE.md`; generated adapters from `tools/sync_harness_adapters.py`.

- [ ] Add one fixture-backed three-chapter end-to-end `MockRunner` test: scope prefix 3 from a five-entry source, crawl `FULL` for workspace scope, sequential translations 1→2→3, QA gate, and requested EPUB/PDF output verification. Stub external EPUBCheck/Calibre calls while retaining real gate and output-file verification. Confirm the summary says `prefix 3 of 5`, not full source. Add explicit old full-book/partial `--max-chapters` regression cases and a changed scope/report/translation hash pause case. Inject crawl/download failure and QA error and assert exit 3 without approval prompt; inject a missing requested PDF and assert export cannot report completed. These tests must avoid live HTTP and native LLM calls.
- [ ] Update `.harness/source/guides/shared-main-agent.md`, `README.md`, and `ARCHITECTURE.md` with creation and existing-workspace commands, confirmed style selection, scope semantics, clean-only `--yes`, `[y/N]`, and headless `--resume --decision` behavior. Do not edit generated `AGENTS.md`/skills directly.
- [ ] Run `uv run python tools/sync_harness_adapters.py`, then `uv run python tools/sync_harness_adapters.py --check` (expect exit 0). Stage only the generated paths actually changed; avoid blanket `git add .claude/` because unrelated worktrees may be present.
- [ ] Run `uv run pytest -q`, `uv run ruff check src tests main.py tools/sync_harness_adapters.py`, and `uv run ruff format --check src tests main.py tools/sync_harness_adapters.py`; each must exit 0. If a failure is new, fix it before claiming acceptance. Commit focused docs/tests/generated adapter files.

## Task 8: Optional disposable live smoke

**Files:** existing `tests/smoke/run_agy_orchestrator.py` (extend rather than introduce an unrelated second launcher), or a separate smoke file only if the existing runner cannot support this mode.

- [ ] Add a `--unified-prefix-smoke` mode that generates a unique slug, preflights `agy`, native translator, EPUBCheck, Calibre, active crawl profile, and source reachability, and invokes the unified command against the supplied Piaotian URL with `--style tien_hiep --limit 3 --formats epub,pdf --yes`. Never remove an existing book workspace.
- [ ] Distinguish product failure from unavailable site/tools. On exit 2, print the crawl/QA report path and warning summary; do not classify the clean-only auto policy as broken. On exit 0, inspect source scope, three selected catalog/state/translation records, current crawl/QA gates, and nonempty EPUB and PDF. Report the unique slug and preserve the workspace for diagnosis unless the operator explicitly requests cleanup.
- [ ] Verify `uv run python tests/smoke/run_agy_orchestrator.py --help` shows the new opt-in mode. Run the live mode only when its dependencies are available and the operator chose to run a live smoke check. Commit the smoke script change separately.

## Final coverage check

| Design requirement | Implementing tasks |
| --- | --- |
| One-command URL init, title/profile fallback, confirmed style | 5, 6 |
| Full-source provenance and immutable prefix catalog | 1, 2, 3 |
| Legacy full-book and partial `--max-chapters` compatibility | 2, 3, 5, 7 |
| Stable lock, pause/reacquire, crash-safe resume policy | 4, 5, 6 |
| Clean-only `--yes`, explicit terminal decision, headless/JSON | 3, 6 |
| Export/QA evidence, fixture acceptance, docs, optional live smoke | 3, 7, 8 |

Before execution, review each task against the linked design again. Keep any implementation changes out of this plan-review commit.
