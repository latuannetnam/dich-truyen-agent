# Unified Orchestrator CLI Design

- **Date:** 2026-09-26
- **Status:** Revised after review; pending user review before implementation planning
- **Builds on:** [2026-09-25 orchestrator design](2026-09-25-orchestrator-langgraph-design.md). Its chapter order, evidence, gate, and runner invariants remain binding.

## 1. Goal and current state

Run a new book from source URL through crawl, translation, QA, and export with one `orchestrate` invocation. A terminal user can decide a paused gate in that same CLI process; a script receives the existing pause and resume contract. A positive prefix limit supports a small, complete *workspace scope* without manual catalog edits.

Today `orchestrate` requires `--workspace`; `crawl-book --max-chapters` limits downloads but retains the full discovered catalog, so the crawl report is partial and the full crawl gate blocks translation. The orchestrator already owns LangGraph approval interrupts, SQLite checkpoints, per-invocation workspace locking, phase bounds, model pins, and exit codes. `RunOutcome` has no `error_count` or `warning_count` fields. `--auto-approve` already approves only clean crawl and QA reports. This design extends those contracts; it does not move approval authority into the CLI.

The first release supports **full-book** and **prefix-limited** new workspaces. Non-prefix `--chapter-range` is deferred: starting at source chapter N > 1 without a valid translation of N-1 violates the sequential-context invariant, and silently renumbering that chapter as 1 would hide the gap. Do not expose a range flag until a separate design specifies predecessor evidence, catalog identity, and export semantics.

The scope choices considered were: (1) trim `chapters.yaml` alone, which passes counts but loses evidence that the source had more chapters; (2) retain the full catalog with a partial crawl approval, which cannot pass the current orchestrator's full gate; and (3) persist the full discovery alongside a selected workspace catalog and bind both to approval hashes. Choose (3). For approval UX, keep the graph interrupt and let the CLI submit a decision, rather than creating a second approval path in the CLI.

## 2. CLI contract

```powershell
$env:PYTHONUTF8=1
uv run python main.py orchestrate --url "<source-index-url>" --slug "<book-slug>" --style tien_hiep --limit 3 --formats epub,pdf --yes

# Existing workspace and phase-bounded commands remain valid.
uv run python main.py orchestrate --workspace books/<book-slug> --start-at qa --stop-after qa
uv run python main.py orchestrate --workspace books/<book-slug> --resume --decision approve
```

| Input | Contract |
| --- | --- |
| `--workspace` | Existing workspace path. If absent, `--url` and `--slug` are both required and derive `books/<slug>`. If provided with `--slug`, the resolved path must be that slug's workspace. |
| `--url` | Required only when creating a workspace. For an existing workspace it must equal `book.yaml`'s source URL; never silently replace the source. |
| `--style` | Required when creating a workspace; must name an existing profile (`general`, `do_thi`, `mat_the`, `tien_hiep`). The explicit value is the operator's genre choice. On an existing workspace, an optional value must match its persisted style; no silent restyling. |
| `--title`, `--author` | Optional on creation. Discover title from the index if omitted; if extraction yields no usable title, block with an actionable request for `--title`. Never persist a placeholder title as real metadata. |
| `--limit N` | Positive integer selecting the first N discovered chapters on a newly initialized, empty-catalog workspace. Omitted means the entire discovered catalog. Reject zero, negative, conflicting scope, and a limit greater than the discovered count. The existing `crawl-book --max-chapters` retains its partial-download meaning. |
| `-y`, `--yes` | Aliases of existing `--auto-approve`: approve only eligible reports with **zero warnings/findings**. A warning still pauses for an explicit operator decision. `--yes` never authorizes harness permission bypass. |
| `--json` | Machine-readable output; never prompt, even if stdin is a TTY. Existing `--resume`, phase bounds, model flags, format selection, and exit codes remain supported. |

Reject creation-only inputs on `--resume` and restore all saved run policy from the run summary: phase span, scope identity, formats, auto-approval setting, timeouts, batch size, model pins, and other execution options. Resume must not turn an unattended run into a different policy because parser defaults were reapplied. To change scope or model, start a new compatible run or a new workspace as appropriate. Validate argument combinations before network access or workspace writes. Emit a bounded, actionable CLI error with exit code 3 for invalid inputs.

## 3. Ownership and execution flow

| Component | New responsibility |
| --- | --- |
| `cli.py` | Parse and validate inputs, call the orchestrator entrypoint, present a compact paused report, and optionally submit a terminal decision. It does not approve a report itself. |
| `orchestrator/orchestrator.py` | Acquire the workspace lock, create or resume the run, pin configuration, and call the graph. Factor its locked start path so auto-initialization and graph startup share **one** lock without recursively acquiring it. Release the lock whenever a graph interrupt returns `paused`; acquire it again on resume, including a resume in the same CLI process. |
| Crawler and workspace domain operations | Discover title and the ordered source catalog; initialize workspace; persist the selected catalog, state, scope evidence, raw files, and crawl report. Preserve existing deterministic profile repair and atomic file operations. |
| LangGraph and approval operations | Reconcile workspace evidence at each phase boundary, handle interrupts and approval writes, and check hash-backed gates. The runner still only supervises native agent processes. |

Add `scope_limit: int | None` to the pinned orchestrator configuration. The graph passes it to the new scoped crawl domain operation; CLI code never slices chapter objects or edits `chapters.yaml` directly.

Use one stable lock path outside the target workspace, derived from its resolved parent/name (for example `<books-root>/.orchestrator-locks/<slug>.lock`), for **all** start and resume paths. This lets a new workspace be locked before creation. Do not unlink the lock file on release: another process may already hold or wait on that file, and unlinking it can create two independent locks. The existing workspace-local lock path must be migrated as part of this change; test simultaneous old/new entry paths rather than assuming they interoperate.

For a new workspace, resolve and validate the target inside the configured books root, then acquire that lock. Read the source index with the existing crawler/profile/browser fallback to obtain a nonempty ordered catalog and title before initializing. If discovery succeeds but title extraction fails and `--title` is absent, return a bounded diagnostic without initializing. If discovery or the profile fails but `--title` was supplied, initialize an empty-catalog workspace and enter the graph's existing crawl/profile-repair path; bind the scope only after successful full discovery. Without a supplied title, such a failure leaves no initialized workspace and asks for `--title` on retry. Validate the chosen style, then initialize `book.yaml`, `chapters.yaml`, `state.yaml`, and `style.yaml` through domain operations. Save the scope record described below before the first crawl approval. Start the existing graph at crawl. If a failure occurs after initialization, preserve the valid workspace and run artifacts for inspection and a compatible retry; never delete or overwrite them automatically.

For an existing initialized workspace, inspect its persisted source, style, catalog, and scope before starting. An empty-catalog workspace may bind its initial scope at first discovery. A nonempty catalog has a frozen scope: reject a new `--limit` that would select different chapters. The ordinary `--workspace` invocation continues to operate that persisted scope. A full-book workspace does not become a prefix workspace merely because a caller supplies `--limit`.

Legacy workspaces without a scope record keep their current full-book gate semantics. Do not invent full-source provenance from an existing `chapters.yaml` that could have been edited. Their already valid hash-backed approvals remain usable under the existing checks, while the new scope-evidence requirement applies to workspaces created by the unified scoped path. A legacy workspace cannot adopt `--limit` in place; use a new workspace or a separately designed migration that rediscovers and compares the source catalog.

## 4. Prefix scope and approval evidence

Discovery must validate the **full source catalog** first, including duplicate URLs, ordering, and parseable chapter-gap blockers. Selection then takes the first N entries. Persist a versioned scope record (for example `reports/source-scope.yaml`) containing source URL, discovery timestamp, the full ordered source entries (position, URL, title, parsed ordinal), their digest and count, selection mode (`full` or `prefix`), requested limit, and selected ordered source IDs/URLs. It contains no chapter bodies. Preserve the source positions and provenance; `chapters.yaml` and `state.yaml` contain only selected chapters with IDs 1..N. Do not conceal a missing source chapter or reassign arbitrary source chapter numbers to close a gap. If the source catalog changes on a later discovery, block with `catalog-changed` and require explicit operator handling; a checkpoint cannot silently inherit a new set of chapters.

Make the crawl report explicit about **source discovered count** and **workspace selected count**. `ApprovalScope.FULL` means every chapter in the frozen workspace scope has valid raw evidence; it does **not** assert that a prefix workspace is the entire source novel. The report and export summary must say `prefix 3 of <source count>` when limited. Update `approval_blockers`, `approve_full_crawl`, and strict gate validation to use the persisted scope, selected catalog, completion counts, and source-validation result together. Hash the scope record, selected catalog, crawl report, and all selected raw files into crawl approval. QA approval continues to hash catalog, state, report, and all selected translations, and must also bind the scope record. An old full-book checkpoint must not be treated as approval of a changed scope, and a scoped checkpoint must not be presented as full-source approval.

The existing `crawl-book --max-chapters` behavior stays a partial-download workflow. Add a distinct scoped-domain entrypoint or explicit selection argument used by the unified flow; do not reinterpret `--max-chapters` or slice a persisted catalog in place. On retries, reuse the frozen selected catalog and download only missing or invalid selected raw chapters. The deterministic report and gate code must reject empty selection, source-catalog blockers, missing selected state/raw evidence, mismatched scope digest, and stale approval hashes before translation.

The workspace scope is immutable once bound by discovery. Expansion or non-prefix selection needs a separate migration workflow and a new design. This keeps predecessor translation lookup correct: chapter 1 is the actual first source chapter, and each later chapter uses its translated predecessor.

## 5. Approval UX and failure behavior

The graph's `interrupt()` remains the sole pause point. `--yes` sets the existing clean-report auto policy before graph execution. Crawl requires full selected scope with no blockers or warnings; QA requires zero findings. Crawl/download failures and QA errors remain `blocked` (exit 3) with a report path and remedy; they are never converted into approval prompts. Missing export tools or outputs likewise remain blocked. Explicit manual approval may accept warnings under the existing gate rules, and the recorded scope and warning count remain visible.

When `RunOutcome.status == "paused"`, the CLI may prompt only if stdin and stdout are TTYs, `--json` is absent, and unattended `--yes` is absent. Load only the typed persisted report and print bounded counts, warning summaries, scope, report path, run ID, and evidence hash. The prompt is `[y/N]`: `y` approves; explicit `n` rejects and ends the run as blocked; Enter or EOF defers and returns the original paused outcome (exit 2). A warning requires the same explicit `y`. Pass the decision to `BookOrchestrator.resume(workspace, decision=...)`; repeat only when that resumed run reaches a *new* pending gate. If the same gate/evidence hash reappears after a decision, stop with a diagnostic instead of prompting forever. A script or agent receives exit 2 and the exact `--resume --decision approve|reject` commands.

Every resume reacquires the workspace lock and rechecks the report and evidence hashes before applying a decision. If files changed while paused, refuse the stale decision and report the required fresh scan/run. Preserve the graph's distinction among `completed` (0), `paused` (2), `blocked` (3), and unexpected `error` (1). Print no raw Chinese or full Vietnamese text. Do not read imaginary counters from `RunOutcome`; inspect typed report fields through bounded domain helpers.

## 6. Verification and acceptance

Use fixtures and a scripted `MockRunner` for automated tests; no live source site or LLM call belongs in the unit/integration suite. Cover:

1. Argument matrix: new URL/slug/style workspace, existing workspace compatibility, mismatch/repeated init, invalid limit, missing metadata, `--resume` pinning, `--json`, and phase-bound behavior.
2. Scope integrity: full discovery validation before prefix selection; exactly N catalog/state/raw/translation records; source count and selection displayed accurately; `FULL` gate for complete selected scope; changed source digest, changed limit, stale hashes, empty/short catalog, and partial `--max-chapters` never pass as a scoped full gate.
3. Approval matrix: clean `--yes` completes; crawl or QA warning with `--yes` pauses; manual `y` resumes through the same run ID; `n` blocks; Enter/EOF and non-TTY pause; errors block; repeated interrupt protection; lock release and reacquisition across pause/resume.
4. Failure recovery: pre-init discovery failure without `--title` leaves no initialized workspace; with `--title`, graph profile repair remains reachable; post-init failure preserves a recoverable workspace; crash/replay does not duplicate approval or chapter promotion; requested PDF requires a nonempty PDF as well as EPUB. Concurrent start/resume attempts share one stable lock and cannot both advance the workspace.
5. Run the repository's current pytest, Ruff, format, and harness sync checks. Do not pin acceptance to a historical test count.

An optional live smoke check uses a **unique disposable slug** and the supplied Piaotian source URL, with `--style tien_hiep --limit 3 --formats epub,pdf --yes`. Preflight `agy`, EPUBCheck, Calibre, profile/site reachability, and native translator availability. Verify the persisted scope record, three selected chapters and translations, current crawl/QA gates, and nonempty EPUB/PDF outputs. A report with warnings correctly exits paused; that is not a failed auto-approval implementation. Record site/tool failures separately from product failures. Never delete an existing `books/tien-phu-truong-sinh` workspace as a test setup step.

## 7. Documentation and rollout

Update `.harness/source/guides/shared-main-agent.md`, `README.md`, and `ARCHITECTURE.md` with the unified command, the distinction between prefix-workspace completeness and full-source completeness, clean-only `--yes`, and interactive/headless resume behavior. Keep the user-confirmed style selection rule. Regenerate root and harness-specific guides/skills with `tools/sync_harness_adapters.py`, then run its `--check` mode. Generated `AGENTS.md`, `CLAUDE.md`, and harness adapters must not be edited directly.

Implementation planning should order the work as: scoped domain/evidence contract; auto-init and lock-safe entry; CLI approval loop; documentation and tests; optional live smoke. Each step must preserve the existing orchestration acceptance matrix.
