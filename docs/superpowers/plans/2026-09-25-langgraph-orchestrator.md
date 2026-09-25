# LangGraph Agent Orchestrator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the approved orchestrator so an initialized book can start at crawl, translation, QA, or export from current workspace evidence, pause/resume safely, and use Antigravity only for bounded profile repair and translation work.

**Architecture:** LangGraph stores a compact execution cursor in SQLite; workspace files, hash-backed gates, and recoverable domain operations remain authoritative. Deterministic code owns discovery/crawl, chapter selection, staging verification, promotion, QA, approval writes, and export. A fresh `agy` process translates one chapter at a time, with configurable model selection; Codex and other harnesses operate the same CLI through generated guidance.

**Tech Stack:** Python 3.13, compatible currently supported LangGraph and SQLite checkpointer releases resolved at implementation time, Pydantic, pytest, uv, existing workspace/domain modules.

**Spec:** `docs/superpowers/specs/2026-09-25-orchestrator-langgraph-design.md` (read Sections 2–10 before each relevant task).

## Global constraints

- Do not implement the former agent-owned coordinator/batch loop, call phase skills from the graph, or use an external LLM API for translation. The four old phase skills become thin CLI entrypoints only in Task 14.
- `batch_size` is a graph checkpoint/progress boundary; each translator `agy` process receives exactly one chapter. Only that translator reads raw/full chapter content into an **agent context**. Deterministic crawler, validator, and QA code may read files internally; graph state, supervising agents, and logs hold only paths, hashes, counts, and bounded diagnostics.
- Full crawl approval must cover a **nonempty** catalog and all raw chapters, including `chapters.yaml` in evidence. QA approval must include `chapters.yaml`, `state.yaml`, the QA report, and all promoted translations. Existing approvals lacking the new evidence are not sufficient for a full-book orchestrator run.
- Chapter `N > 1` needs a completed, hash-valid translation of `N-1`. Keep 3 launches per pending chapter per run, 2 profile-repair sessions per run, and separate child-process timeouts. Agent success text or exit code cannot certify a domain result.
- Defaults: `--start-at auto`, `--stop-after export`, `--batch-size 5` (explicit flag then `.env` then default), `--chapter-timeout 1800`, `--agent-timeout 1800`, `--crawl-timeout 21600`, `--profile-repair-attempts 2`, `--formats epub,azw3`. EPUB is required; MOBI/PDF require explicit selection.
- `--agy-model` is the default for agent invocations; `--agy-translation-model` overrides only chapter translation. Explicit models are checked on the target installation and pinned on resume. A QA-only/export-only run does not need `agy`.
- Windows commands set `PYTHONUTF8=1` and workspace-local `UV_CACHE_DIR`. Launch child processes with argv and `shell=False`; terminate the entire tree on timeout/cancel. No permission bypass by default.
- Existing `cli.main()` prints `OperationResult` and currently leaves blocked/error commands with exit code 0. The new `orchestrate` command alone must return 0 completed, 2 paused, 3 blocked, 1 error, without changing older CLI contracts incidentally.

Use this shell setup for all implementation tests:

```powershell
$env:PYTHONUTF8=1
$env:UV_CACHE_DIR="$PWD\.uv-cache"
```

For each code task, write the stated behavioral test, run its named pytest command and observe the relevant failure, implement the contract, rerun the same test green, then commit only the files owned by that task. Documentation and the external capability record are verified by review and their stated commands. Tests must assert persisted files and calls, not mirror a branch condition inside the implementation.

## File map and dependency order

| Unit | Files | Responsibility |
| --- | --- | --- |
| Capability record/dependencies | `docs/superpowers/plans/2026-09-25-agy-capability.md`, `pyproject.toml`, `uv.lock` | Verify target `agy` and select compatible LangGraph/checkpointer versions before runner implementation. |
| Workspace domain | `workspace.py`, `glossary.py`, `checkpoints.py`, `crawl_reports.py`, `crawl_profiles.py`, `cli.py` | Strict chapter context, attempt-scoped staging, recoverable promotion, profile probe, strengthened approval evidence, crawl JSON. |
| Process/harness | `orchestrator/process.py`, `orchestrator/runners/{base,agy,mock}.py` | Supervise CLI trees and capture bounded results; never decide domain success. |
| Execution | `orchestrator/{models,state,workspace_ops,graph,orchestrator,tracer}.py` | Validated config, phase entry, graph routing, retry/approval journals, lock, summaries, CLI-facing run/resume. |
| Operator surface | `cli.py`, `.harness/source/**`, `tools/sync_harness_adapters.py`, generated guides/adapters, `README.md`, `ARCHITECTURE.md` | Expose phase spans and migrate every harness guide/skill to the single orchestrator CLI. |
| Tests | `tests/orchestrator_support.py`, `tests/test_orchestrator_*.py`, existing domain/generator tests | Build real hash-valid workspace fixtures, cover spec's E01–E15, R01–R15, C01–C08, and real optional smoke. |

Do not land generated guides/skills before the CLI exists. Domain and mock-runner work can proceed when `agy` is absent, but do not mark the Antigravity capability gate or real smoke test passed until a target installation is exercised.

Test snippets below show the contract being asserted. Create the named fixtures in each task's test module from `tests/orchestrator_support.py`; they must use real workspace files and approval hashes. The shared `MockRunner` is introduced in Task 7.

### Task 1: Capability gate and compatible dependencies

**Files:** Create `docs/superpowers/plans/2026-09-25-agy-capability.md`; modify `pyproject.toml`, `uv.lock`; create `tests/test_orchestrator_dependencies.py`.

**Interface:** Record the verified executable/version, headless prompt form, direct `ag_translator` selection, `agy models` behavior, output status/exit codes, permission behavior, and effective-model visibility. Later tasks use this record to implement `AgyRunner`; they must not invent flags.

- [ ] Run a harmless command (`agy --version`, `agy --help`, `agy models`, and agent listing supported by that version) on the target machine. Use a disposable workspace for one native agent invocation, nested-file restriction, stdout/stderr, timeout, and cancellation checks. Record exact commands/results and permission requirements in the capability file. If unavailable, record the blocker and continue only deterministic/mock tasks.
- [ ] Resolve a Python 3.13-compatible, currently supported `langgraph` and `langgraph-checkpoint-sqlite` pair, inspect the chosen checkpointer/interrupt APIs and safe deserialization setting, add exact resolved versions to `uv.lock`, and record them. Do not reuse the old plan's broad `>=0.2`/`>=2.0` ranges.
- [ ] Write a dependency smoke test that imports the exact APIs selected above, then a separate test that persists one small state with a fixed thread ID, reopens SQLite, and verifies the same state. Run red before adding dependencies and green after the lockfile update. The import test starts with:

```python
def test_langgraph_sqlite_modules_import():
    from importlib import import_module

    assert import_module("langgraph.graph")
    assert import_module("langgraph.checkpoint.sqlite")
```

- [ ] Run `uv run pytest tests/test_orchestrator_dependencies.py -q` and `uv lock --check`. Commit only the capability record, dependency/test changes, and lockfile after both checks pass. A missing `agy` capability remains explicitly unverified, not a passing test.

### Task 2: Strict translation work item and attempt-scoped staging

**Files:** Modify `src/dich_truyen_agent/workspace.py`, `src/dich_truyen_agent/cli.py`; extend `tests/test_translation.py`; create `tests/orchestrator_support.py`, `tests/test_orchestrator_staging.py`.

**Interface:** Add a domain work-item variant that accepts `run_id` and positive `attempt`, returns paths under `reports/runs/<run_id>/staging/`, and passes those same paths to verification/promotion. Keep legacy fixed staging behavior for older low-level CLI use until cutover, but the orchestrator never uses it.

- [ ] First write tests for: chapter 1 has no predecessor; chapter `N > 1` blocks when predecessor file is absent or hash-invalid; a completed chapter after a pending one blocks; candidate staging outside the canonical run directory or from another attempt is rejected; leftover fixed-name staging cannot satisfy a new attempt.
- [ ] In `tests/orchestrator_support.py`, create builders for an initialized two-chapter workspace, full crawl gate with actual catalog/report/raw hashes, translated prefix, and current QA gate. Return an object with `root`, `catalog`, `state`, and report paths; keep all later matrix fixtures grounded in these files rather than mocked gate booleans.

```python
def test_attempt_paths_are_isolated(workspace_with_crawl_gate):
    first = next_translation_work_item(workspace_with_crawl_gate, run_id="run-a", attempt=1)
    second = next_translation_work_item(workspace_with_crawl_gate, run_id="run-a", attempt=2)
    assert first.data["staged_txt"] != second.data["staged_txt"]
    assert second.data["state"] == "pending"
```

- [ ] Make `prepare_translation_context` and the orchestrator work-item path verify predecessor status, path, and SHA256 before returning absolute context paths; remove the later-chapter `prev_translation_path = null` fallback. Validate every supplied run/attempt staging path with `validate_workspace_relative_path` plus the exact run staging prefix.
- [ ] Extend `verify_staged_chapter` and promotion signatures to take the attempt identity/path pair; reject path traversal, mismatched chapter IDs, stale files, empty text, invalid heading, and malformed proposals before canonical writes. Keep `OperationResult` compact; do not put chapter text in JSON.
- [ ] Run `uv run pytest tests/test_translation.py tests/test_orchestrator_staging.py -q` and commit this isolated domain change.

### Task 3: Recoverable chapter promotion

**Files:** Modify `src/dich_truyen_agent/workspace.py`, `src/dich_truyen_agent/glossary.py`; create `tests/test_orchestrator_promotion.py`.

**Interface:** Provide `recover_chapter_promotion(workspace, chapter_id) -> OperationResult` and an orchestrator promotion entrypoint taking `run_id`/`attempt`; `WorkspaceOps` calls recovery before interpreting chapter state. A durable journal records chapter/attempt, before/after hashes for canonical text, glossary, conflict report, and state.

- [ ] Write failpoint tests after each replacement (canonical file, glossary/conflict report, state). Add a test-only write wrapper that raises after a chosen replacement while production calls use normal atomic storage writes. Reopen the workspace, recover once, recover again, and assert exactly one completed chapter, one glossary merge, expected SHA256s, and no agent retranslation. Mutate an input between failpoint and recovery and assert `BLOCKED`, not an overwrite.

```python
def test_recovery_is_idempotent(workspace_with_staged_chapter, fail_after_glossary):
    fail_after_glossary.enable()
    promote_chapter_translation(workspace_with_staged_chapter.root, 1, run_id="run-a", attempt=1)
    assert recover_chapter_promotion(workspace_with_staged_chapter.root, 1).status is OperationStatus.OK
    assert recover_chapter_promotion(workspace_with_staged_chapter.root, 1).status is OperationStatus.OK
    assert inspect_workspace(workspace_with_staged_chapter.root).status is OperationStatus.OK
```

- [ ] Prepare all replacement payloads and hashes before the first write. Atomically persist the journal, then atomically replace each target. Recovery rolls forward only when actual hashes match either recorded before/after values, blocks on divergence, and removes the journal only after complete verification. Preserve manual/legacy promotion behavior through the existing CLI until migration is complete.
- [ ] Run `uv run pytest tests/test_orchestrator_promotion.py tests/test_glossary.py tests/test_workspace.py -q`; commit.

### Task 4: Full-scope crawl and QA evidence, reusable approval operations

**Files:** Modify `src/dich_truyen_agent/checkpoints.py`, `src/dich_truyen_agent/crawl_reports.py`, `src/dich_truyen_agent/cli.py`; extend `tests/test_checkpoints.py`, `tests/test_crawl_reports.py`, `tests/test_qa.py`.

**Interface:** Move approval logic now embedded in `cli.py` into domain functions `approve_full_crawl(workspace, report)` and `approve_current_qa(workspace, report, allow_warnings)`; CLI remains a wrapper. Both return typed `OperationResult`. Never auto-approve a report with warnings.

- [ ] Write failing tests for empty catalog, partial crawl, missing raw chapter, warning/error report, and old approvals missing `chapters.yaml`. Verify new crawl evidence includes catalog plus report/raw but not mutable `state.yaml`. Verify QA evidence includes catalog, state, report, and every completed translation; changing any one invalidates QA approval.

```python
def test_new_crawl_gate_tracks_catalog_not_mutable_state(full_crawl_workspace):
    result = approve_full_crawl(full_crawl_workspace.root, full_crawl_workspace.report)
    assert result.status is OperationStatus.OK
    full_crawl_workspace.promote_first_translation()
    assert check_gate(full_crawl_workspace.root, CheckpointType.CRAWL_APPROVED).status is OperationStatus.OK
```

- [ ] Make full-book approval require `discovered_count > 0`, `scope == FULL`, `selected_count == discovered_count == completed_count`, no blockers, and fresh report/raw evidence. Apply the stricter evidence contract to orchestrator gate checks; older partial/legacy approvals block with a regeneration instruction. Manual QA may accept warnings using partial scope; automatic QA requires zero findings.
- [ ] Run `uv run pytest tests/test_checkpoints.py tests/test_crawl_reports.py tests/test_qa.py -q`; commit.

### Task 5: Deterministic crawl JSON, candidate probe, and local profile install

**Files:** Modify `src/dich_truyen_agent/cli.py`, `src/dich_truyen_agent/crawl_profiles.py`, `src/dich_truyen_agent/crawl_batch.py`; create `src/dich_truyen_agent/crawl_probe.py`, `tests/test_orchestrator_crawl.py`, `tests/test_crawl_probe.py`.

**Interface:** `crawl-book --json` emits exactly one parseable `OperationResult` on stdout. `probe_crawl_profile(workspace, candidate_path) -> OperationResult` is read-only: it uses the existing parser/crawler with bounded first/middle/last chapter samples and reports catalog URL order/content threshold. `install_local_profile` replaces only the workspace override after a passing probe.

- [ ] Test an empty initialized catalog entering discovery, a nonempty catalog skipping discovery and downloading only missing/failed raw artifacts, and a zero-chapter result that cannot be approved. Assert `--max-chapters 0` and configured delay reach `crawl_book` and that an `OperationStatus.BLOCKED` JSON remains blocked even if the CLI process exits 0.
- [ ] Test schema/domain mismatch, wrong/empty index, content below threshold, changed URL order with existing state, and first/middle/last extraction using local HTTP/HTML fixtures; assert the probe makes no book/catalog/state/raw/profile writes.

```python
def test_probe_rejects_changed_catalog_order(existing_catalog_workspace, candidate_profile):
    before = existing_catalog_workspace.catalog.read_bytes()
    result = probe_crawl_profile(existing_catalog_workspace.root, candidate_profile)
    assert result.status is OperationStatus.BLOCKED
    assert "catalog-changed" in result.reason
    assert existing_catalog_workspace.catalog.read_bytes() == before
```

- [ ] Add `--json` to `crawl-book`; keep diagnostics on stderr so stdout is one JSON result. Validate candidate with existing schema/domain rules plus `probe_crawl_profile`, atomically install the local override, and retain previous profile/candidate diagnostics in the run directory. Never call `promote-crawl-profile` or mutate the shared domain template.
- [ ] Run `uv run pytest tests/test_orchestrator_crawl.py tests/test_crawl_probe.py tests/test_crawl_batch.py tests/test_crawl_profiles.py -q`; commit.

### Task 6: Shared Windows-safe process supervisor

**Files:** Create `src/dich_truyen_agent/orchestrator/process.py`, `tests/test_orchestrator_process.py`.

**Interface:** `run_process(argv, *, cwd, env, timeout_seconds, stdout_path, stderr_path, on_event) -> ProcessResult` launches with `shell=False`, drains stdout/stderr concurrently to bounded or rotating files, and kills/reaps the full process tree on timeout or cancellation. It reports exit code, timeout/cancel flags, timestamps, paths, and bounded failure detail.

- [ ] Create fixture child scripts that (a) exit nonzero, (b) run quietly longer than a short wall clock limit, (c) fill both pipes, and (d) spawn a grandchild. Assert no deadlock, no false idle timeout, separate stream logs, and no live descendant after timeout/cancel.

```python
def test_quiet_child_uses_wall_clock_not_idle_timeout(process_fixture):
    result = run_process(process_fixture.quiet_argv, timeout_seconds=2, **process_fixture.paths)
    assert result.exit_code == 0
    assert result.timed_out is False
```

- [ ] On Windows bind the child to a Job Object with kill-on-close; on POSIX launch a new session and signal its process group. Wait for descendants and pipe readers, then flush logs. Keep in-memory excerpts capped and scrub secrets/chapter text from structured events. Use the same supervisor for deterministic crawl and `agy`.
- [ ] Run `uv run pytest tests/test_orchestrator_process.py -q`; commit. The descendant test must execute, not be skipped, on the target Windows platform.

### Task 7: Antigravity runner, native agent dispatch, and model routing

**Files:** Create `src/dich_truyen_agent/orchestrator/runners/{__init__,base,agy,mock}.py`, `tests/test_orchestrator_agy_runner.py`, `tests/test_orchestrator_mock_runner.py`.

**Interface:** Implement the spec's keyword-only `HarnessRunner.run_phase(phase, workspace, prompt, model, timeout_seconds, on_event) -> HarnessRunResult`. The verified `AgyRunner.build_command(agent_name, prompt, model, timeout_seconds) -> list[str]` builds argv without a shell. The runner reports process facts only; `WorkspaceOps` decides domain success. `MockRunner` records exact calls and returns scripted outcomes.

- [ ] From Task 1's capability record, implement only verified `agy` headless and direct custom-agent options. Test the argv vector uses `--model <slug>` when specified, `ag_translator` for one chapter and `ag_metadata_translator` for metadata, and never defaults to a permission-bypass flag; the flag appears only for explicit `--allow-harness-permission-bypass`. Add a test proving the prompt contains absolute file paths/IDs but no chapter text.
- [ ] Test `agy models` preflight: an explicitly requested unavailable slug returns a typed blocker before launch; global model applies to metadata/profile repair/translation, and translation override changes translation only. An omitted model passes no `--model` and logs the effective model as unknown unless CLI metadata reports it.

```python
def test_model_is_a_distinct_argv_item(agy_runner):
    command = agy_runner.build_command("ag_translator", "Translate chapter 1", "literary", 1800)
    assert command.count("--model") == 1
    assert command[command.index("--model") + 1] == "literary"
```

- [ ] Feed subprocess JSON/text/stream events according to the verified target version; preserve separate stdout/stderr logs and do not invent structured tool-call/thought events when the CLI supplies plain text. A successful CLI response without the expected candidate/staging artifact is still an unsuccessful domain attempt.
- [ ] Run `uv run pytest tests/test_orchestrator_agy_runner.py tests/test_orchestrator_mock_runner.py -q`; commit. If Task 1 did not prove direct `ag_translator`, stop this task and amend the design with the user before choosing another runner shape.

### Task 8: Compact config/state, attempt journal, and tracing

**Files:** Create `src/dich_truyen_agent/orchestrator/{__init__,models,state,tracer}.py`, `tests/test_orchestrator_models.py`, `tests/test_orchestrator_attempts.py`, `tests/test_orchestrator_tracer.py`.

**Interface:** `OrchestratorConfig` validates CLI/`DICH_TRUYEN_TRANSLATION_BATCH_SIZE`/default precedence and persists selected span, formats, timeouts, repair budget, model choices, and approval mode. `BookOrchestratorState` matches spec Section 5. `AttemptJournal` atomically records `(run_id, chapter_id, attempt)` or a profile-repair session before launch. `ActivityTracer` writes compact `run_summary.json` plus one bounded log per invocation.

- [ ] Test valid/reversed phase spans, positive timeout/batch values, default formats, `.env` batch-size precedence, UUID run IDs, and serialization of a state with no raw text/arrays. Test the attempt count across journal reopen and crash before process launch.

```python
def test_attempt_budget_survives_reopen(tmp_path):
    journal = AttemptJournal(tmp_path / "attempts.json")
    assert journal.reserve("run-a", 7, limit=3) == 1
    assert AttemptJournal(tmp_path / "attempts.json").reserve("run-a", 7, limit=3) == 2
```

- [ ] Implement atomic journal writes and per-run isolation; a new run gets fresh chapter/profile-repair budgets while `--resume` uses the same record. Store `current_chapter_id`/`chapter_attempt` and `profile_repair_attempts` in graph state as display snapshots only, not as the authoritative budgets.
- [ ] Test concurrent stdout/stderr log writes, log rotation/bounds, compact progress, requested versus CLI-reported model, pending gate/report path, and no raw/full translated text in state or summary. Do not promise tool/thought events unless capability-proven.
- [ ] Run `uv run pytest tests/test_orchestrator_models.py tests/test_orchestrator_attempts.py tests/test_orchestrator_tracer.py -q`; commit.

### Task 9: WorkspaceOps and phase-entry reconciliation

**Files:** Create `src/dich_truyen_agent/orchestrator/workspace_ops.py`, `tests/test_orchestrator_phase_entry.py`.

**Interface:** `WorkspaceOps.inspect_entry(workspace, start_at, stop_after) -> EntryDecision` resolves workspace evidence and the earliest selected incomplete phase. It calls existing domain operations, not mirrored YAML rules. It can return `completed`, `enter:<phase>`, or `blocked:<reason>`; no child process is started here.

- [ ] Build hash-valid initialized, full-crawl, translated, and QA-approved fixture states. Parameterize the ten valid explicit phase spans, six reversed spans, four `auto` endpoints, and missing/partial/stale prerequisite variations from E01–E15. Assert later explicit starts never backtrack into earlier phases and that no prior SQLite history is needed.

```python
def test_export_entry_uses_workspace_not_graph_history(qa_approved_workspace):
    decision = WorkspaceOps().inspect_entry(qa_approved_workspace.root, "export", "export")
    assert decision.phase == "export"
    assert decision.status == "enter"
```

- [ ] Reconcile `inspect_workspace`, full crawl scope/evidence, `next_translation_work_item`, current QA gate, and requested export artifacts. For QA/export entry verify complete, gap-free translation hashes, not only state counts. A current QA gate is reusable without rewriting its timestamped report. A satisfied non-export endpoint is a no-op; explicit export may regenerate requested formats.
- [ ] Run `uv run pytest tests/test_orchestrator_phase_entry.py tests/test_workspace.py tests/test_checkpoints.py -q`; commit.

### Task 10: Graph crawl, automatic local profile repair, and crawl approval

**Files:** Create `src/dich_truyen_agent/orchestrator/graph.py`; create `tests/test_orchestrator_crawl_graph.py`, `tests/test_orchestrator_approval.py`.

**Interface:** `build_orchestrator_graph(ops, runner, tracer, checkpointer)` routes the selected span. Crawl node uses Task 6's deterministic subprocess and Task 5's typed JSON/probe; only profile failures dispatch the Task 7 agent. The approval-decision node calls `interrupt()` with a compact report/evidence fingerprint and has no side effects before it.

- [ ] Test empty catalog -> discovery before report, nonempty complete raw -> report first, pending raw -> crawl remaining, full/warning/blocker report outcomes, and automatic profile repair for missing domain profile, index selector, and chapter selector. Assert no agent call on normal crawl.
- [ ] Test candidate-only agent writes, schema/domain/live first-middle-last probe, catalog URL-order compatibility, local override install, retry from existing raw progress, two-session ceiling **across crash/resume**, repeated candidate/failure signature stop, `no_safe_profile_fix` on outage/CAPTCHA, no shared profile promotion, and unauthorized mutation detection. Reserve each repair session in the Task 8 journal before launching it.

```python
def test_crawl_warning_auto_policy_pauses(graph_fixture):
    outcome = graph_fixture.run(crawl_warning=True, auto_approve=True, stop_after="crawl")
    assert outcome.status == "paused"
    assert graph_fixture.calls.count("approve_full_crawl") == 0
```

- [ ] Test manual crawl approval resumes only with unchanged persisted report and raw/catalog hashes; altered evidence yields a new report/decision. Approval write occurs in a separate node; a crash after that write rechecks the gate and skips duplicate approval. Block zero discovered chapters and partial scope even when `failed_count == 0`.
- [ ] Run `uv run pytest tests/test_orchestrator_crawl_graph.py tests/test_orchestrator_approval.py -q`; commit.

### Task 11: Graph metadata and one-chapter translation loop

**Files:** Extend `src/dich_truyen_agent/orchestrator/graph.py`, `workspace_ops.py`; create `tests/test_orchestrator_translation_graph.py`.

**Interface:** The graph calls `ag_metadata_translator` only for missing translated metadata. It then processes up to `batch_size` *sequential* chapters per graph batch, launching a fresh direct `ag_translator` process per chapter. The graph owns retries, staging verification, promotion, and next-work-item selection.

- [ ] Test first pending chapter selection, predecessor path/hash validation, one agent process per chapter, distinct run/attempt staging paths, correct model override, metadata no-op after valid update, and compact batch checkpoint after the configured count. The runner receives only absolute paths/ID, not raw or translated text.

```python
def test_two_chapters_use_two_fresh_agent_calls(translation_graph_fixture):
    outcome = translation_graph_fixture.run(chapters=2, batch_size=2)
    assert outcome.status == "completed"
    assert [call.phase for call in translation_graph_fixture.runner.calls] == [
        "chapter_translation", "chapter_translation"
    ]
```

- [ ] Before each launch, reserve attempt in the durable journal and snapshot protected hashes. After exit, recover a pending promotion journal first, reject unauthorized workspace edits, then verify only this attempt's staging and run domain promotion. Requery canonical chapter status regardless of process exit/agent JSON. Retry only transient/process, staging, and correctable glossary/structure failures up to three total launches, with bounded backoff; stale gate/gap/missing predecessor/divergent journal blocks immediately.
- [ ] Inject crash after staging and after each promotion write. Assert resume neither promotes stale output nor retranslates an already valid promoted chapter. A post-promotion process error still counts the valid chapter once; an out-of-order promotion or more than `batch_size` new chapters in a graph batch blocks.
- [ ] Run `uv run pytest tests/test_orchestrator_translation_graph.py tests/test_orchestrator_staging.py tests/test_orchestrator_promotion.py -q`; commit.

### Task 12: Deterministic QA, approval, and export graph paths

**Files:** Extend `src/dich_truyen_agent/orchestrator/graph.py`, `workspace_ops.py`; create `tests/test_orchestrator_qa_export.py`.

**Interface:** QA uses existing `check-translation`/domain logic and a separate approval node; export uses `export_book` and verifies every requested file. Neither phase invokes `agy`. Direct QA/export entries are permitted from valid workspace evidence without earlier graph runs.

- [ ] Test current QA gate reuse without report rewrite, QA errors -> `blocked: needs repair`, warning report -> manual pause even with `--auto-approve`, zero findings -> auto approval, manual warning approval -> recorded partial scope, and changed translation/report/state evidence -> fresh decision. Assert no translation rerun from a QA error.

```python
def test_export_only_never_starts_harness(qa_export_graph_fixture):
    outcome = qa_export_graph_fixture.run(start_at="export", stop_after="export")
    assert outcome.status == "completed"
    assert qa_export_graph_fixture.runner.calls == []
```

- [ ] Test direct export with valid full crawl and QA gates, default `epub,azw3`, explicit MOBI/PDF, missing EPUBCheck, missing Calibre for a requested derivative, and output file absence despite a success result. Recheck QA gate immediately before export; skip all earlier phases. On crash after one artifact, resume verifies or regenerates requested outputs and completes only when all exist.
- [ ] Run `uv run pytest tests/test_orchestrator_qa_export.py tests/test_qa.py tests/test_export.py -q`; commit.

### Task 13: Durable run lifecycle, SQLite resume, lock, and CLI

**Files:** Create `src/dich_truyen_agent/orchestrator/orchestrator.py`; modify `src/dich_truyen_agent/cli.py`; create `tests/test_orchestrator_lifecycle.py`, `tests/test_orchestrator_cli.py`.

**Interface:** `BookOrchestrator.start(config) -> RunOutcome` creates UUID run/thread ID and manifest; `BookOrchestrator.resume(workspace, decision=None) -> RunOutcome` reopens the saved thread/config and reconciles workspace before replay. CLI exposes all Section 7 flags. Result includes status, run ID, selected span, pending approval/report, next resume command, and exit code.

- [ ] Test `--start-at auto|crawl|translate|qa|export`, `--stop-after`, model/timeout/format/approval options including opt-in `--allow-harness-permission-bypass`, invalid phase order/budget, `--resume` combined with selectors/model, decision without pending interrupt, and model choices pinned on resume. Assert exit codes 0/2/3/1 by invoking `main.py` in a subprocess rather than only mocking `run_command`.
- [ ] Test a paused run's plain new invocation reports the pending resume, explicit new `--start-at` marks the old run `superseded`, superseded resume fails, and a new run can start from a later valid workspace gate without any previous SQLite thread. Test workspace lock contention, release on pause/exit, and reacquisition on resume.

```python
def test_new_phase_run_has_new_thread_id(run_harness, crawl_approved_workspace):
    first = run_harness.start(crawl_approved_workspace.root, start_at="translate", stop_after="translate")
    second = run_harness.start(crawl_approved_workspace.root, start_at="qa", stop_after="qa")
    assert first.run_id != second.run_id
    assert second.selected_span == ("qa", "qa")
```

- [ ] Store one SQLite checkpoint file per run under `reports/runs/<run_id>/`, so its history can be retained or removed without editing another run's state. The manifest atomically records current run ID/status and prevents simultaneous writers. Use LangGraph `interrupt()` only for approval decisions; call `Command(resume=...)` or the verified equivalent for the locked version. On replay, check workspace gates and promotion journal before repeating side effects. Keep `thread_id == run_id`, not the book slug. Define retention: preserve active/paused run databases and every run summary; prune only a terminal run's database after 30 days while holding the workspace lock, with a test that a paused run is never pruned.
- [ ] Add CLI parsing/dispatch and explicit `sys.exit` handling for `orchestrate` only; preserve existing commands' output behavior. Print compact pause instructions, status, run ID, span, and report path. `--resume` keeps original span/model config, while a new explicit phase call creates a new run.
- [ ] Run `uv run pytest tests/test_orchestrator_lifecycle.py tests/test_orchestrator_cli.py -q`; commit.

### Task 14: Generated AGENTS.md, skills, and harness migration

**Files:** Modify `.harness/source/manifest.json`, `.harness/source/guides/shared-main-agent.md`, `.harness/source/guides/panels/{ag,cc,oc,codex,cw}.md`, `.harness/source/skills/{crawl-book,translate-book,check-translation,export-book}.md`, `tools/sync_harness_adapters.py`, generated `AGENTS.md`, `CLAUDE.md`, `opencode.json`, and prefixed skill/agent outputs; create `.harness/source/skills/orchestrate-book.md`; update `README.md`, active `ARCHITECTURE.md` examples, and existing generator/guide tests named in spec Section 2.1.

**Interface:** Every harness operator skill calls the same orchestrator CLI. There is no additional harness runner; only the generated `ag_translator` and `ag_metadata_translator` definitions are needed for agent execution. The generator owns all generated copies and removes only explicitly listed obsolete generated paths.

- [ ] Update source guide with sections for development and operation, including style confirmation before `init-book`, phase entry/resume commands, gate review/approval flow, model flags, compact diagnostics, test commands, and no direct chapter reading in a supervising agent. Remove the coordinator dispatch/whole-book loop from current guidance.
- [ ] Create `orchestrate-book` as the shared operator procedure. Rewrite four phase skills as thin span mappings: crawl/crawl, translate/translate, qa/qa, export/export; no skill directly runs `approve-*`, `promote-chapter`, chapter translation, or its own retry loop. Generate prefixed variants for AG, CC, OC, and Codex. Cowork uses CC skills but invokes the CLI with its Linux `uv run --isolated --python 3.13` form.

```python
def test_phase_skill_maps_to_cli(generated_translate_skill):
    text = generated_translate_skill.read_text(encoding="utf-8")
    assert "--start-at translate --stop-after translate" in text
    assert "next-translation-work-item" not in text
    assert "invoke_subagent" not in text
```

- [ ] Change manifest/generator rendering for the new skill and Antigravity-only generated translator/metadata adapters; retire generated coordinator, inactive CC/OC/Codex translator adapters, old translation dispatch fragments, and Claude translation workflow. Rebuild `opencode.json` permissions from the new manifest. Have `--check` report obsolete generated outputs as well as missing/stale current ones, and have normal generation remove only listed generated legacy files with a verified workspace-contained path.
- [ ] Revise `tests/test_harness_source_contract.py`, `test_harness_generator_check.py`, `test_harness_adapter_discovery.py`, `test_main_guides_generated.py`, `test_ag_md_references.py`, and Cowork guide tests. Assert generated header/frontmatter, consistent CLI mapping, no active coordinator instructions, and no accidental deletion of an unrelated user file. Update current README/ARCHITECTURE usage while leaving historical ADRs recognizable as past behavior.
- [ ] Run `uv run python tools/sync_harness_adapters.py`, `uv run python tools/sync_harness_adapters.py --check`, and the named generator/guide tests; commit source and generated artifacts together. Do this only after Task 13's CLI exists.

### Task 15: Exhaustive deterministic acceptance matrix

**Files:** Create `tests/test_orchestrator_matrix_entry.py`, `tests/test_orchestrator_matrix_resume.py`, `tests/test_orchestrator_matrix_contract.py`; reuse domain/mock fixtures from prior tasks.

**Interface:** These are black-box orchestrator tests with real workspace files/hashes and scripted `MockRunner`, not mocks of gate outcomes. The `orchestrator_fixture` records `called_phases` separately from the public `RunOutcome`. Tests implement spec IDs E01–E15, R01–R15, and C01–C08; record ID in each test name or pytest parameter ID so coverage is auditable.

- [ ] Parameterize all ten valid explicit phase spans, six invalid reversed spans, and four `auto` endpoints. For every E case assert status/exit, exactly selected phase calls, correct gate/file hashes, and no earlier/later side effects. Include new direct translation/QA/export without a prior graph thread, satisfied phase no-op, explicit export regeneration, and absent/partial/stale prerequisites.
- [ ] Inject R failures after crawl raw write, approval write, metadata write, staging, each promotion replacement, QA report/approval, and one export output. Restart the *same* run with `--resume`, prove same thread ID and model choices, and assert no duplicate promotion/approval or disallowed phase call. Separately prove explicit new phase creates a new run and supersedes a paused run.

```python
@pytest.mark.parametrize("start,stop", [
    ("crawl", "crawl"), ("crawl", "translate"), ("crawl", "qa"), ("crawl", "export"),
    ("translate", "translate"), ("translate", "qa"), ("translate", "export"),
    ("qa", "qa"), ("qa", "export"), ("export", "export"),
])
def test_valid_spans_enter_only_selected_phases(orchestrator_fixture, start, stop):
    outcome = orchestrator_fixture.run(start_at=start, stop_after=stop)
    assert outcome.selected_span == (start, stop)
    order = ("crawl", "translate", "qa", "export")
    assert all(order.index(start) <= order.index(phase) <= order.index(stop)
               for phase in orchestrator_fixture.called_phases)
```

- [ ] C tests assert model routing/invalid slug, agent output never trusted over domain files, protected-file mutation detection, no external LLM/API calls, CLI status/log contract, and generated guide/skill consistency. Use local fixtures only; no live site, external agent, or network in the default test suite.
- [ ] Run `uv run pytest tests/test_orchestrator_matrix_entry.py tests/test_orchestrator_matrix_resume.py tests/test_orchestrator_matrix_contract.py -q`; commit only when all 38 named cases and the span matrix pass.

### Task 16: Full verification and opt-in real smoke

**Files:** Create `tests/smoke/run_agy_orchestrator.py`; update `README.md`/`ARCHITECTURE.md` only for verified smoke findings. The script creates a disposable two-chapter workspace and local fixture HTTP server without touching user books.

- [ ] Run the full local suite and quality checks on Windows with `PYTHONUTF8=1` and local `UV_CACHE_DIR`:

```powershell
uv run pytest -q
uv run ruff check src tests main.py tools/sync_harness_adapters.py
uv run ruff format --check src tests main.py tools/sync_harness_adapters.py
uv run python tools/sync_harness_adapters.py --check
git diff --check
```

- [ ] On the capability-verified Antigravity installation, serve a disposable two-chapter fixture site on localhost, deliberately break its workspace-local profile, and run the smoke through automatic profile repair, explicit model selection, direct one-chapter translator invocations, manual pause/resume, QA, and EPUB export. Confirm log paths, same-run resume, model report provenance, no raw chapter text in run summary, and correct default/explicit format handling. This is opt-in because it launches a native agent and local HTTP server.
- [ ] If the real `agy` gate or smoke cannot run on this machine, report those checks as **unverified** and do not claim the full orchestrator acceptance gate passed. Fix any failures, rerun the affected tests and full suite, review final diff against the spec's E/R/C matrix, then commit the final verified changes.

## Spec coverage map

| Design spec section | Plan tasks that implement and verify it |
| --- | --- |
| 1 and 5.1: selected phase spans and prerequisite evidence | 9, 13, 15 |
| 2: ownership and strengthened hash gates | 2–4, 9–12, 15 |
| 2.1: generated AGENTS.md and harness skill migration | 14, 15 |
| 3: Antigravity capability, permissions, and model validation | 1, 6–7, 16 |
| 4 and 5: runner interface, compact graph state, workspace operations | 6–13 |
| 5.2: deterministic crawl, local profile repair, approval | 4–5, 10, 15–16 |
| 5.3: metadata, one-chapter translation, staging, promotion | 2–3, 7–8, 11, 15–16 |
| 5.4 and 5.5: deterministic QA and export | 4, 9, 12, 15–16 |
| 6: crash/resume, retry budgets, interrupts, locks | 3, 6, 8, 10–13, 15 |
| 7 and 8: CLI, exit codes, logs, artifact retention | 8, 13, 15–16 |
| 9 and 10: dependency order and acceptance tests | 1–16 |

## Completion checklist

- [ ] Phase entry: all ten valid explicit spans, six invalid spans, four `auto` endpoints, and no prior-thread direct starts verified.
- [ ] Resume: approval interrupts, evidence changes, crash boundaries, attempt/promotion journals, lock/supersession, and model pinning verified.
- [ ] Crawl/profile: deterministic normal path, guarded candidate probe/local install, bounded repair, full nonempty approval evidence verified.
- [ ] Translation: metadata once, one native agent per chapter, strict predecessor, attempt-scoped staging, recoverable promotion, three attempts verified.
- [ ] QA/export: no `agy` on direct deterministic runs, gate hashes, warning policy, requested format verification verified.
- [ ] Generated guides/skills: CLI-only operator path, no coordinator/legacy adapter discoverability, generator `--check` clean.
- [ ] Full suite, lint/format, Windows child-tree timeout, and real opt-in Antigravity smoke results reported distinctly.
