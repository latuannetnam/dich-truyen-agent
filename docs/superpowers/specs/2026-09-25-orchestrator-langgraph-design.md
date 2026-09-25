# Agent Orchestrator with LangGraph and Harness Runner Abstraction (Agy-first)

- **Date:** 2026-09-25
- **Status:** Revised design, pending review
- **Initial harness:** Antigravity CLI (`agy`), subject to the capability check in Section 3
- **Engine:** LangGraph StateGraph with SQLite checkpoints

## 1. Goal and boundaries

Run a previously initialized novel workspace through any selected span of crawl, translation, QA, and export with bounded agent sessions, durable pause/resume, and compact operational logs. A new run may start directly at a later phase when its prerequisite workspace evidence is current; it never has to replay earlier phases merely because there is no older LangGraph thread. The orchestrator manages the lifecycle; existing workspace files and checkpoint gates remain authoritative. It never reads raw Chinese chapters or full Vietnamese translations into graph state or logs, and it never calls an external LLM API to translate.

An `orchestrate` run requires an existing workspace created by `init-book` with the user-confirmed style. Book initialization, source metadata selection, and style choice are outside this command. Entry into translation or any later phase requires a full crawl approval covering the discovered catalog. Partial crawl approvals remain useful for other workflows but cannot silently become full-book orchestration approvals.

The first implementation supports one workspace and one active orchestrator process at a time. Codex, Claude Code/Cowork, and OpenCode can develop or operate the orchestrator through the CLI and generated guidance, but Antigravity is the only initial agent-execution backend. Their native subagent runners are possible future implementations, not part of the initial acceptance criteria. Avoid adding empty runner stubs until a second harness has a tested command and result contract.

## 2. Ownership and invariants

| Component | Owns | Does not own |
| --- | --- | --- |
| Workspace domain operations | `state.yaml`, `book.yaml`, `chapters.yaml`, reports, approvals, promoted chapters, export artifacts | Agent process lifecycle |
| LangGraph | Phase routing, approval interrupts, run identity, pause/resume cursor, and bounded translation batch checkpoints | Authoritative chapter or gate status |
| Harness runner | Starting and stopping one CLI process, capturing its output, reporting exit/timeout | Deciding that a chapter or gate passed |
| Antigravity agent | Diagnosing crawl failures and proposing a workspace-local profile repair, translating metadata, or translating exactly one chapter into staging per invocation | Routine HTTP crawling, choosing chapters, promoting translations, approving gates, or running a batch loop |

At every phase boundary and after every harness exit, derive chapter progress and gate validity again from workspace domain operations. Graph counters are snapshots for display only. `check-gate` and the hash-backed evidence determine whether an approval is current. Extend new crawl approval evidence to include `chapters.yaml`, and new QA approval evidence to include `chapters.yaml` and `state.yaml`; the existing approval commands do not hash these files today. Do not include mutable `state.yaml` in crawl evidence, because chapter promotion changes it. Reject older approvals missing the required catalog evidence for an orchestrated full-book run and guide the operator to regenerate them. `next-translation-work-item` determines whether translation is pending, completed, or blocked. A `blocked` result, a chapter gap, or stale evidence stops execution; it is never treated as a transient process failure.

The orchestrator owns the compact sequential translation loop. One fresh Antigravity process runs the native `ag_translator` for **one chapter only** and writes only staged text and optional glossary proposals; `batch_size` limits the number of chapters the graph processes before a checkpoint and progress summary, not the number translated in one agent process. The current `$ag-translate-book` skill and `ag_coordinator` describe a different, agent-owned loop. Do not invoke either from the orchestrator. Migrate the active harness guidance and skills to the orchestrator contract in Section 2.1 so they cannot restart the old agent-owned loop. The translator instructions remain sourced from `.harness/source/agents/translator.md`, not copied into an ad hoc prompt.

### 2.1 AGENTS.md and harness skill migration

`AGENTS.md` is a generated, cross-harness guide for **developing and operating the orchestrator**, not a recipe for a main agent to execute pipeline steps itself. Keep `.harness/source/guides/shared-main-agent.md` authoritative and regenerate root `AGENTS.md` and `CLAUDE.md`; never hand-edit generated copies. Its operations section explains initialization and user-confirmed style, `orchestrate --start-at/--stop-after`, `--resume` and approval decisions, model flags, status/exit codes, current workspace gates, and how to report a blocked run. Its development section points to the spec, shared harness source, adapter generator, test suite, and the rule that deterministic crawl, verification, promotion, QA, and export belong to the orchestrator/domain code. Preserve context isolation and the ban on external LLM API translation. Human approval policy stays in the orchestrator; a supervising Codex/Claude/OpenCode/Antigravity agent reports the pending decision and submits `--resume --decision ...` only after the user has decided.

Add one shared `orchestrate-book` operator skill, generated as `ag-orchestrate-book`, `cc-orchestrate-book`, `oc-orchestrate-book`, and `codex-orchestrate-book`. It chooses an explicit phase span from the user's request, runs the single `orchestrate` CLI entrypoint, reads compact status/report paths, and gives the correct resume command. Keep the four existing prefixed phase skill names as **thin compatibility entrypoints**: `crawl-book` maps to `--start-at crawl --stop-after crawl`; `translate-book` maps to `translate/translate`; `check-translation` maps to `qa/qa`; `export-book` maps to `export/export`. They link to the shared operator procedure and contain no independent loops, gate approval, chapter-file reads, or harness-native translator dispatch. Running any skill with an absent/stale prerequisite returns the orchestrator's blocker; it does not backtrack or manually repair the workspace. Skills may pass approved CLI options such as `--agy-translation-model`, but may not override the orchestrator's retry or evidence decisions.

The initial runtime has one agent backend: Antigravity CLI. Other harnesses use their terminal capability to operate or help develop that CLI; their own subagent tools do not translate chapters or substitute for `agy`. Retain `ag_translator` and `ag_metadata_translator` as generated native Antigravity definitions for the runner. Remove `ag_coordinator` and the inactive `cc_*`, `oc-*`, and `codex_*` translator/coordinator adapters from active generation, along with the Claude `translate-book.js` workflow and old per-harness translation dispatch fragments. Keep the canonical translator instruction source for the Antigravity adapter. A future non-Antigravity runner requires its own capability gate and design amendment before enabling agent execution. Simplify the Cowork panel to its CLI environment syntax and remove its general-agent translation fallback; retain the generated `CLAUDE.md` panel for harness guidance.

Update `.harness/source/manifest.json`, `tools/sync_harness_adapters.py`, panel guides, `opencode.json` skill policy, and adapter discovery tests together. Revise `tests/test_harness_source_contract.py`, `test_harness_generator_check.py`, `test_harness_adapter_discovery.py`, `test_main_guides_generated.py`, `test_ag_md_references.py`, and the Cowork-specific guide tests so they assert the new contract rather than old coordinator text. Update the active workflow examples in `README.md` and `ARCHITECTURE.md`; preserve historical ADRs as historical records. The generator's `--check` must detect **obsolete generated files as well as missing/stale current files**, and normal generation must remove only listed generated legacy outputs, never arbitrary user files. Run generation, then `--check`, and assert that no discoverable skill or root guide still instructs direct `approve-crawl`, `approve-qa`, `promote-chapter`, coordinator dispatch, or a whole-book agent loop. Existing low-level CLI commands remain available for domain testing and manual repair, but are not the operator skill path.

## 3. Antigravity capability gate

Before implementing `AgyRunner`, run a small, non-destructive capability check on the target installation and record its results in the implementation plan:

1. Locate the executable and capture its version/help. Verify the actual non-interactive prompt syntax, direct custom-agent selection, output mode, timeout options, permission behavior, and exit codes. Google documents `agy models` and session-level `--model`, but the exact command and direct `ag_translator` support on the target installation still need a smoke test. Do not hard-code the previously proposed `agy -p ... --dangerously-skip-permissions --print-timeout ...` command from this spec.
2. Confirm that a fresh CLI session discovers the project `ag_translator` and `ag_metadata_translator` definitions, can invoke the translator directly for exactly one chapter with its configured model, can write only the designated staging outputs, and can run a bounded profile-repair task. Confirm the translator's effective model when the CLI exposes it; do not infer subagent model inheritance from `model: inherit`. If direct custom-agent dispatch is unavailable, fail the translation capability gate and revise the design explicitly before implementation; do not silently restore a coordinator loop or use an external LLM API.
3. Confirm what machine-readable events the CLI exposes. If it only provides text, logging may stream text, but tool calls and agent thoughts must not be claimed as structured events.
4. Prove that timeout or cancellation ends the entire child process tree on Windows. Confirm `stdout` and `stderr` can be drained without blocking and that a quiet, still-running process is not mistaken for a hang.

If this gate fails, stop before a run that could require agent work and report the missing capability. A QA-only or export-only run uses deterministic operations and does not require `agy` to be installed. A crawl run with pending crawl work checks the capability because automatic profile repair may need the agent; translation checks it before a chapter or metadata task. A run whose selected endpoint is already satisfied needs no harness. The runner launches an argument vector with `shell=False`, sets `PYTHONUTF8=1`, uses the project root as `cwd`, and resolves the workspace to an absolute path. Any permission bypass is an explicit operator option, limited to the intended workspace and recorded in the run summary; it is not the default.

## 4. Architecture and interfaces

```text
src/dich_truyen_agent/orchestrator/
    __init__.py
    orchestrator.py       # run/resume API and workspace lock
    graph.py              # nodes and conditional routes
    state.py              # compact checkpoint state
    workspace_ops.py      # typed facade over existing deterministic operations
    process.py            # shared subprocess, timeout, and process-tree supervisor
    tracer.py             # live display and bounded log persistence
    models.py             # config, outcomes, and event schemas
    runners/
        base.py           # HarnessRunner protocol
        agy.py            # verified Antigravity CLI adapter
        mock.py           # controlled tests
```

`WorkspaceOps` reuses the existing deterministic crawler, crawl reporting/approval, `check_gate`, `next_translation_work_item`, staged-chapter verification, glossary validation/promotion, QA, QA approval, and export. The orchestrator invokes `crawl-book` as a supervised Python subprocess, not through an agent. Add a JSON result mode to that CLI command so `WorkspaceOps` can parse its `OperationResult` even when the process exits with code 0. The process supervisor applies the same Windows process-tree timeout handling to deterministic crawl and harness calls. Where approval logic currently lives inside `cli.py`, move that logic into a small domain function and leave the CLI as a thin wrapper. The orchestrator must not duplicate domain criteria. Every operation returns a typed `OperationResult`; `status`, report data, and current gate checks determine the route. The current CLI prints `blocked`/`error` without a nonzero process exit code, so exit code alone is insufficient.

```python
class HarnessRunner(Protocol):
    def run_phase(
        self,
        *,
        phase: Phase,
        workspace: Path,
        prompt: str,
        model: str | None,
        timeout_seconds: int,
        on_event: Callable[[RunEvent], None],
    ) -> HarnessRunResult: ...

# HarnessRunResult includes exit_code, timed_out, cancelled,
# started_at, ended_at, stdout/stderr log paths, and failure detail.
# It does not claim domain success.
```

The runner receives prompts only for profile repair, metadata translation, and one chapter translation. QA and export use deterministic workspace operations rather than skills that also approve or have different format defaults. Metadata translation, if `translated_title` or a present author translation is missing, is a separate bounded harness invocation before the first chapter; it uses the existing native metadata translator and persists through `update-book-metadata`.

`--agy-model <slug>` selects the default model for every agent invocation in this run. `--agy-translation-model <slug>` overrides it for chapter translation only; if both are omitted, the CLI's configured default applies. Pass a selected slug as a distinct `--model` argv element, never by shell interpolation or by editing user/global Antigravity settings. Validate explicitly selected slugs against the target installation's `agy models` output before the first relevant invocation; an unavailable slug blocks the run without fallback. Persist the requested model per phase and the model reported by the CLI when available; label an unreported effective model as unknown. Explicit selections are pinned in the run config and reused on `--resume`; an unpinned CLI default may change outside the run and must be shown as such in the run summary. Neither option changes an existing translated chapter or starts an agent for a phase that is already complete.

## 5. Graph state and execution

Checkpoint state holds only compact data:

```python
class BookOrchestratorState(TypedDict):
    workspace: str                 # absolute canonical path
    run_id: str                    # UUID; also the LangGraph thread_id
    harness: str
    config: dict                   # validated batch, timeout, format, approval, model settings
    start_at: str                  # auto, crawl, translate, qa, export
    stop_after: str                # crawl, translate, qa, export
    phase: str
    batch_index: int
    current_chapter_id: int | None
    chapter_attempt: int           # display snapshot; durable attempts live in run journal
    profile_repair_attempts: int
    pending_approval: str | None   # crawl or qa
    approval_report_hash: str | None
    status: str                    # running, paused, blocked, completed, error, superseded
    error_code: str | None
    error_message: str | None
    run_dir: str
```

Do not checkpoint raw source text, chapter translations, full report bodies, per-chapter arrays, or verbose logs. Display counters are computed from workspace state at the time of rendering. Store the SQLite file under the workspace run metadata directory, and store the current `run_id` in a small run manifest. A compact, atomically written per-run attempt journal records chapter ID and attempts *before* each agent launch so a crash cannot reset the retry budget. `orchestrate --resume` resolves that ID and uses the same LangGraph `thread_id`; it retains the run's `start_at`, `stop_after`, and explicit model selections. A new invocation after a terminal `blocked` or `completed` run gets a new ID and reconciles the workspace. While a run is paused, a plain new invocation reports the pending resume; an explicit `--start-at` creates a new run, marks the old one `superseded` in its summary, and prevents later resumption of that thread. A workspace lock prevents simultaneous writers; release it when the CLI exits in `paused` state and reacquire it on resume or a new run.

### 5.1 Phase entry and bounded runs

`--start-at` selects the first phase the caller wants the new run to consider. `--stop-after` selects the last phase to complete; its default is `export`. `auto` chooses the earliest incomplete phase within the requested endpoint from workspace evidence, or completes immediately if that endpoint is already satisfied. An explicit start never runs an earlier phase to repair a missing prerequisite: it returns `blocked` with the missing or stale gate and the command needed to prepare it. A selected phase that is already complete is skipped, except an explicit `export` invocation may regenerate its requested formats. Once `stop_after` is satisfied, the run ends successfully with its selected span in the summary; it does not enter later phases. Require `stop_after` to be the same as or later than an explicit `start_at`.

| New run starts at | Required workspace evidence before entry | Completion of that phase |
| --- | --- | --- |
| `crawl` | Initialized `book.yaml`, style, catalog/state (empty is allowed) | Current full `crawl-approved` checkpoint, including catalog and raw evidence |
| `translate` | Current **full** `crawl-approved` checkpoint; nonempty catalog; valid raw evidence | Every catalog chapter promoted in order; `next-translation-work-item` returns `completed` |
| `qa` | Current full crawl checkpoint and complete, gap-free translations | Current `qa-approved` checkpoint after QA/approval; an existing current QA gate may be reused |
| `export` | Current full crawl checkpoint, complete translations, and current `qa-approved` checkpoint | Every requested format verified in `exports/` |

Translation has durable per-chapter promotions in `state.yaml` and translation files, but no separate `translation-completed` approval checkpoint today. The QA entry check therefore validates the catalog/state pairing and hashes of all completed translation artifacts through `inspect_workspace`, then requires `next-translation-work-item` to return `completed`; it must not treat a numeric count alone as proof. The QA checkpoint can be partial when a human accepted warnings, matching the current export gate behavior; automatic QA approval still requires zero findings. Gate checks must validate current hashes and the strengthened evidence requirements in Section 2. Checking prerequisites does not run their phases.

An explicit `--start-at qa` with a current QA gate and `--stop-after qa` is a successful no-op. An explicit `--start-at export` runs export using existing approvals without re-running crawl, translation, or QA. An explicit `--start-at translate` begins at the first pending chapter without opening a crawl subprocess. These new runs use new graph thread IDs even if an earlier orchestrator run never existed; a valid workspace is sufficient.

```mermaid
flowchart TD
    Start([new run or resume]) --> Inspect[reconcile workspace and selected span]
    Inspect -->|auto or non-export endpoint already satisfied| Done([completed selected span])
    Inspect -->|explicit translate, prerequisites valid| Metadata[ensure translated metadata]
    Inspect -->|explicit qa, prerequisites valid| QA[run deterministic QA]
    Inspect -->|explicit export, prerequisites valid| Export[deterministic export]
    Inspect -->|explicit entry prerequisite invalid| Blocked([blocked])
    Inspect -->|crawl gate valid and full, later endpoint| Metadata[ensure translated metadata]
    Inspect -->|catalog empty or raw incomplete| Crawl[deterministic discover and download]
    Inspect -->|nonempty catalog and raw ready, gate missing| CrawlReport[build and validate crawl report]
    Crawl -->|success| CrawlReport
    Crawl -->|crawl/profile failure| Repair[agent proposes local profile candidate]
    Repair --> Probe[validate and probe candidate]
    Probe -->|valid and retry budget left| Crawl
    Probe -->|invalid or no safe repair| Blocked
    CrawlReport -->|catalog or extraction blocker| Repair
    CrawlReport -->|other blockers or incomplete scope| Blocked([blocked])
    CrawlReport -->|eligible| CrawlDecision{auto policy or approval interrupt}
    CrawlDecision -->|auto policy refuses warnings| Paused([interrupt: manual review])
    CrawlDecision -->|approved| ApproveCrawl[approve and recheck crawl gate]
    CrawlDecision -->|rejected| Blocked
    ApproveCrawl -->|stop after crawl| Done
    ApproveCrawl --> Metadata
    Metadata --> NextItem[requery next work item]
    NextItem -->|pending| Chapter[run one isolated translator for one chapter]
    NextItem -->|blocked or error| Blocked
    Chapter --> StageCheck[verify staging and promote through domain operation]
    StageCheck --> Reconcile[requery chapter state and artifacts]
    Reconcile -->|promoted, batch has room| NextItem
    Reconcile -->|promoted, batch boundary| Checkpoint[save compact batch checkpoint]
    Checkpoint --> NextItem
    Reconcile -->|retryable failure, chapter budget left| Chapter
    Reconcile -->|blocked or attempts exhausted| Blocked
    Reconcile -->|all complete| QA[run deterministic QA]
    NextItem -->|completed| QA
    NextItem -->|stop after translate, completed| Done
    Reconcile -->|stop after translate, completed| Done
    QA -->|existing QA gate current| Export
    QA -->|errors| NeedsRepair([blocked: needs repair])
    QA -->|eligible| QADecision{auto policy or approval interrupt}
    QADecision -->|approved| ApproveQA[approve and recheck QA gate]
    QADecision -->|rejected| Blocked
    ApproveQA -->|stop after qa| Done
    ApproveQA --> Export[deterministic export]
    QA -->|existing QA gate, stop after qa| Done
    Export -->|required formats verified| Done
    Export -->|failed or blocked| Blocked
```

### 5.2 Crawl and crawl gate

On entry, validate `book.yaml`, `chapters.yaml`, `state.yaml`, style, and workspace path. A workspace freshly created by `init-book` has an empty catalog and state; this is valid *before discovery*, not a crawl result. If an existing **full** `crawl-approved` gate is current, skip crawl. Otherwise, when `chapters.yaml` is empty, call crawl work immediately. For an existing nonempty catalog, build a report first and run crawl work only if raw chapters are missing or failed. After the harness exits, rebuild the report and inspect `approval_blockers(report)`, `discovered_count`, `selected_count`, `completed_count`, `scope`, and warnings. Do not infer readiness from `failed_count == 0`. The full-book path requires `discovered_count > 0`, `scope == FULL`, `selected_count == discovered_count`, `completed_count == selected_count`, and no blockers. A zero-chapter catalog is always blocked from approval, even if the report currently contains no blocker.

For a new book, the orchestrator reads `source_url` and slug from `book.yaml` and runs the existing deterministic `crawl-book` operation with the workspace's books root, `--max-chapters 0`, and the configured chapter delay. That operation loads the active source-domain profile, fetches the index with its declared encoding and browser fallback, discovers and validates chapter links, writes `chapters.yaml` and matching pending chapter records in `state.yaml`, then downloads chapter bodies sequentially into `raw/`. It validates extraction, uses browser fallback and bounded retries where appropriate, writes each successful raw file and hash atomically, and skips valid completed raw files on a later invocation. A resumed crawl with a nonempty catalog reuses that catalog and downloads only pending, failed, or invalid raw artifacts. The agent is not involved in this normal path.

For a crawl or profile failure after the crawler's own bounded retries, or a catalog/extraction blocker in the crawl report, the orchestrator automatically dispatches a fresh `agy` profile-repair session. This includes a missing domain profile, failed index discovery, invalid selectors, failed chapter extraction, or invalid discovered catalog. The agent receives the source URL, active profile (if any), a compact error and report excerpt, and paths to bounded sample pages as needed. It may inspect the source site and proposes a replacement **only** in a candidate file under the current run directory; it does not call `approve-crawl`, promote a shared profile, or write `chapters.yaml`, `state.yaml`, or raw chapters. Give the repair session only the paths it needs; snapshot critical workspace file hashes before dispatch and block if the agent changed anything outside its candidate/log area. A transient outage, CAPTCHA requiring human action, workspace corruption, or a cancellation may yield `no_safe_profile_fix`; the agent must not invent a selector change merely to force a retry. Report warnings are not errors: with `--auto-approve`, unresolved warnings pause for manual review rather than silently approving or repeatedly redownloading already completed chapters.

The orchestrator validates the candidate's schema and domain with the existing `validate-crawl-profile` rules, then runs a new read-only functional probe using the same crawler/parser code: fetch the index, require a nonempty catalog with no blockers, and extract representative first, middle, and last chapters above the configured content threshold. The existing `validate-crawl-profile` CLI checks schema and domain only, so this live probe is a required new deterministic operation. If the workspace already has a nonempty catalog, the probe also compares chapter URL order against it. A mismatch is `catalog-changed` and blocks automatic replacement; the existing `crawl-book` resume path would otherwise reuse stale links. If translations or crawl approval already exist, do not automatically rebuild a catalog or replace raw evidence. A valid candidate with compatible catalog is atomically installed as workspace `crawl-profile.yaml`, and the orchestrator retries deterministic `crawl-book` from the current workspace state. Retain the previous local profile and candidate diagnostics in the run directory for inspection. Never promote a local repair into the shared domain template automatically.

Permit at most two profile-repair sessions per orchestrator run, each followed by one validated crawl retry. The crawler's own per-chapter HTTP retries are a separate budget. Stop early if the agent returns no valid candidate, the same profile hash recurs, the functional probe fails, or the failure signature repeats without raw-chapter progress. Record the last crawl error, candidate/probe outcome, and remaining work in `run_summary.json`; finish as `blocked` rather than looping indefinitely.

Neither the normal crawl subprocess nor the profile-repair agent approves crawl. The existing crawl skill combines crawling and approval, so the orchestrator does not invoke it. Auto-approval requires full scope, no blockers, and no warnings; warnings pause for a manual decision. Manual approval is a LangGraph `interrupt()` with a compact report summary and report path. The approval node must have no side effects before `interrupt()`. Save hashes of the persisted report and the raw evidence covered by it with the pending request; on resume, compare both against the current files before applying the decision. Changed evidence requires a fresh report and decision. After approval, call the shared approval operation and verify `check_gate` and full scope again.

### 5.3 Translation

After the crawl gate, ensure metadata translation is complete through a separate native `ag_metadata_translator` invocation when needed. At each batch start and after every chapter, read `next-translation-work-item --json` or its domain equivalent. The orchestrator checks the current full crawl gate, catalog/state continuity, the target raw artifact, and the completed/hash-valid predecessor translation for every chapter after chapter 1. Missing or corrupt predecessor evidence blocks; the existing `prepare_translation_context` fallback that sets `prev_translation_path = null` for a later chapter is not allowed in this path and must be tightened. `next-translation-work-item` deterministically creates the chapter glossary context and provides absolute input/output paths. The orchestrator passes only these paths and the chapter ID to a fresh, direct `ag_translator` session. The agent reads source/context, makes linguistic choices, writes staged text and optional glossary proposals, self-reviews, and returns compact status; it never promotes or selects the next chapter.

Before **each** launch, the orchestrator records the attempt durably and allocates fresh staging paths under the run directory using the chapter ID and attempt number. Extend the work-item and verify/promote domain interfaces to accept this attempt identity and its staged paths; old fixed-name staging files are quarantined and cannot satisfy a new attempt. The domain operation validates that supplied paths are inside the current run's staging directory. Snapshot hashes of protected workspace state (`book.yaml`, `chapters.yaml`, `state.yaml`, glossary, prior promoted translations, and approvals) before dispatch. A translator may write only its two designated staging paths; unexpected mutations block and require repair. Keep raw and full translation text out of the prompt, graph state, and logs.

After the process ends, regardless of exit code or claimed success, reconcile any promotion journal before interpreting chapter status. If the chapter is already promoted and its file/hash/state are valid after recovery, count it once and advance. Otherwise accept only the current attempt's staged files, run `verify-staged-chapter`, then the full glossary consistency and promotion operation. The agent's JSON is diagnostic, not proof of a translated chapter. The existing `promote_chapter_translation` writes the canonical text, then merges glossary, then updates `state.yaml`; those writes are individually atomic but the group is not. Before using it unattended, prepare the intended canonical text, glossary/conflict report, and state writes, recording their before/after hashes and chapter/attempt identity in a durable promotion journal **before** the first replacement. On replay, compare actual files to those hashes: finish missing replacements only when inputs still match, accept a fully committed chapter once, and block on divergent files. Remove the journal only after all outputs and state hashes are verified. Resume must never overwrite an already promoted valid chapter, silently accept a half-merged glossary, or retranslate because the process crashed after successful promotion.

The orchestrator owns one retry budget of three agent launches **per pending chapter per run**, counting the initial launch. Retry only process failures, missing/invalid staging, or a correctable glossary/structure failure; include the bounded validation reason in the next prompt and use polite backoff. A stale gate, state gap, missing predecessor, unexpected agent mutation, or unrecoverable promotion state blocks immediately. Persist the attempt count before launch so `--resume` cannot reset it. On success, reset the current chapter attempt snapshot and continue to the next chapter in catalog order. A graph batch handles at most `batch_size` newly promoted chapters, saves a compact checkpoint, then starts a fresh batch if work remains. Progress is valid only for the expected chapter ID and valid canonical hash; an out-of-order promotion or jump beyond the batch limit is a contract violation. No batch-level zero-progress retry counter remains.

### 5.4 QA and QA gate

First check whether the existing `qa-approved` gate is current. If it is, proceed to export without regenerating the report: the existing QA report has a generated timestamp, so rewriting it would make its hash-backed approval stale. Otherwise run `check-translation` through deterministic workspace operations, persist `reports/qa-report.yaml`, and inspect the typed report. Any `error_count > 0` enters `blocked: needs repair` with report path; it does **not** route to translation when all chapters are complete. A later new run rechecks QA after operator repair. The orchestrator does not automatically edit translated chapters or glossary entries.

For manual mode, present errors/warnings and obtain an explicit decision through `interrupt()` before approval. For `--auto-approve`, require **zero findings** and a fresh report. This is stricter than the existing `approve-qa` command, which permits warnings and records partial scope. Manual approval may accept warnings using that existing behavior; the decision and warning count are recorded. On resume, compare the persisted report hash and hashes of all translations covered by QA; do not regenerate the report merely to test freshness. Changed evidence requires a new QA scan and decision. Then call the shared `approve-qa` operation and verify `check_gate` before export.

### 5.5 Export

Export through the deterministic `export_book` operation. Default requested formats are `epub,azw3`; MOBI and PDF require an explicit `--formats` value. EPUB is required. Every explicitly requested format must have a successful result and an output file before the orchestrator reports `completed`. If Calibre is missing and a requested derivative is skipped, report `blocked` with the actionable export result; do not silently mark the run successful. Recheck the QA gate before export. The output format policy belongs to the orchestrator config, not to a free-form agent prompt.

## 6. Resume, retries, and failure handling

Workspace files win whenever a SQLite snapshot and file state differ. Graph checkpoints are execution cursors, not transactions spanning CLI child processes and workspace writes. Each side-effecting node must recheck its precondition at entry and its postcondition on exit. A replayed node may skip work already proven complete, but must not overwrite a promoted chapter or create duplicate approvals based solely on its checkpoint state.

`interrupt()` is used only in approval-decision nodes; approval writes happen in separate nodes after resume. The CLI must surface pending approval and exit as `paused`, rather than waiting on stdin during an unattended run. `--resume --decision approve|reject` resumes the current pending interrupt using the saved thread ID. `--resume` without `--decision` resumes a crash or stopped run only when no approval decision is pending. Resume keeps the original phase span; combining `--resume` with `--start-at` or `--stop-after` is invalid. To start a different phase, create a new run with `--start-at`; that needs valid workspace evidence, not the old run's SQLite checkpoint. Rejection ends that run as `blocked`. After correcting workspace data or rejecting a gate, a new invocation starts a new run and reevaluates the workspace. If a process crashed after approval but before its graph checkpoint, the replay checks the existing gate and skips the approval write.

Timeouts are wall-clock limits on individual harness and deterministic crawl subprocess invocations. Set separate defaults for one chapter agent, metadata/profile-repair agents, and a potentially much longer crawl, all configurable. A lack of stdout alone is not a hang signal. On timeout or cancellation, terminate the whole child process tree, wait for pipes to close, flush logs, then reconcile workspace and the promotion journal before retrying or stopping. Unexpected graph/domain errors surface as `error`; gate failures and operator-repair cases surface as `blocked`. No phase retries indefinitely.

## 7. CLI contract

```powershell
$env:PYTHONUTF8=1
uv run python main.py orchestrate --workspace books/<slug> `
    [--start-at auto|crawl|translate|qa|export] `
    [--stop-after crawl|translate|qa|export] `
    [--harness agy] [--auto-approve] [--batch-size 5] `
    [--agy-model <slug>] [--agy-translation-model <slug>] `
    [--chapter-timeout 1800] [--agent-timeout 1800] [--crawl-timeout 21600] `
    [--profile-repair-attempts 2] `
    [--formats epub,azw3] [--log-level compact|verbose] `
    [--allow-harness-permission-bypass]

uv run python main.py orchestrate --workspace books/<slug> --resume
uv run python main.py orchestrate --workspace books/<slug> --resume --decision approve
uv run python main.py orchestrate --workspace books/<slug> --resume --decision reject

# New run from an existing full crawl checkpoint: translate only
uv run python main.py orchestrate --workspace books/<slug> --start-at translate --stop-after translate --agy-translation-model <slug>

# New run using existing crawl and QA evidence: export only
uv run python main.py orchestrate --workspace books/<slug> --start-at export --stop-after export
```

These commands describe the interface to implement; they are not present in `main.py` yet. Effective batch size follows explicit CLI argument, project `.env` `DICH_TRUYEN_TRANSLATION_BATCH_SIZE`, then default 5. `--chapter-timeout` applies to each translator process; `--agent-timeout` applies to metadata and profile-repair processes. Validate positive sizes/timeouts and nonempty model slugs; validate `--profile-repair-attempts` as a nonnegative integer, default 2. Explicit model slugs are checked against `agy models` only when their phase may launch an agent; an export-only run does not require `agy`. `--resume` rejects new model flags and reuses the saved choices; to change a model, start a new run at the needed phase. `--auto-approve` is an opt-in policy for eligible reports, not permission for an agent to approve its own work. The CLI prints the run ID, selected phase span, status, pending gate/report path when paused, and the next resume command. Exit codes are 0 for completed, 2 for paused, 3 for blocked, and 1 for unexpected error; internal routing still uses typed operation results rather than exit codes alone.

## 8. Tracing and artifacts

Use an unambiguous UUID run directory under `books/<slug>/reports/runs/<run_id>/` with a compact `run_summary.json` and one log per harness invocation. Persist timestamps, phase, chapter ID/attempt, process exit/timeout, before/after chapter counts, report paths, gate decisions, requested model slug per invocation, CLI-reported effective model if available, requested formats, and final outcome. The terminal shows phase milestones and elapsed time. Drain stdout and stderr concurrently, preserving their source. Raw text logs are bounded or rotated for long runs and are not copied into LangGraph state. Avoid recording secrets and full chapter contents; verbose mode means available CLI output, not a promise of private agent thoughts or structured tool-call events. SQLite checkpoints need a retention/cleanup policy for completed runs, while run summaries remain available for diagnosis.

## 9. Dependencies and implementation sequence

After the Antigravity capability gate, resolve a **compatible, currently supported** LangGraph and SQLite checkpointer pair for Python 3.13, then commit exact versions in `uv.lock`. Do not carry forward the earlier `langgraph>=0.2,<1` and `langgraph-checkpoint-sqlite>=2,<3` ranges without checking the current APIs and resolver. Configure the SQLite checkpointer's safe deserialization options if required by the selected release.

Implement in this order: (1) capability check for direct custom-agent invocation and model selection; (2) deterministic chapter context/validation and recoverable promotion; (3) deterministic crawl JSON result, read-only profile probe, and shared approval operations; (4) shared process supervisor and Antigravity runner; (5) graph, attempt journal, and SQLite resume; (6) tracer and CLI; (7) shared harness guide/skill migration and generated-adapter cleanup from Section 2.1, after the CLI contract exists; (8) acceptance suite and real smoke run. Keep old operator skills active only until the new CLI is ready, then switch generated guidance and skill entrypoints together so users do not see instructions for a nonexistent command. This order proves the chapter and crawl contracts before building the graph around them.

## 10. Acceptance tests

1. A mock two-batch full-book run creates only full crawl approval, advances chapters sequentially, passes QA, and exports the requested formats.
2. Manual crawl and QA gates pause before approval. No skill or subprocess approves them. Resume with the same thread ID and unchanged report succeeds; changed report/evidence requires a fresh decision.
3. A newly initialized empty-catalog workspace enters discovery before any crawl report or approval decision. Zero discovered chapters cannot be approved. Auto-approval refuses crawl blockers, partial crawl scope, crawl warnings, QA errors, and QA warnings. Manual QA may approve warnings and records that decision. Changing `chapters.yaml` invalidates either approval; changing `state.yaml` after QA invalidates QA approval without invalidating the earlier crawl approval.
4. The orchestrator invokes one fresh native translator per chapter, in catalog order. Each graph batch promotes no more than `batch_size` chapters before checkpointing; the agent cannot choose another chapter or promote canonical files. A gap or promotion beyond the bound blocks immediately.
5. A process crash after `promote-chapter`, after crawl approval, and after QA approval resumes without repeating completed work or losing the next pending chapter.
6. `OperationResult.status == blocked/error` is honored even when the deterministic CLI process exits with code 0. Timeout ends all descendants and captures both output streams.
7. Three agent launches for one chapter exhaust that run's budget, including launches across crash/resume. A failed attempt's stale staging is rejected. A later chapter gets its own budget; domain blockers are never retried automatically.
8. QA errors in an otherwise fully translated book enter `needs repair` without a translation loop. A new run after repair reruns QA.
9. Missing EPUBCheck blocks required EPUB export. Missing Calibre blocks an explicitly requested derivative; the default and configured format policies are tested separately.
10. A missing profile, broken index selector, and broken chapter selector each invoke an isolated agent repair session, validate a workspace-local candidate, and retry deterministic crawl. The agent never approves crawl or changes book state directly; an attempted unauthorized workspace mutation is detected and blocks the run. An invalid candidate, repeated signature with no progress, and exhausted repair budget block cleanly.
11. A read-only profile probe rejects an empty/wrong catalog and chapter extraction below threshold. A changed catalog order with existing state blocks automatic replacement instead of retrying against stale links. A repaired local profile does not change the shared domain template.
12. A real two-chapter Antigravity smoke workspace proves profile repair, direct `ag_translator` selection, exactly one chapter per agent process, explicit `--model` selection, logs, SQLite pause/resume, and EPUB output before attempting a long unattended run. An invalid explicit model fails before translation and never falls back silently.
13. A fresh `--start-at crawl --stop-after crawl` run accepts an empty catalog, stops after a valid crawl approval, and never enters metadata or translation. A fresh `--start-at translate --stop-after translate` run succeeds using a valid crawl checkpoint without an earlier graph run or a crawl call; missing, stale, or partial crawl approval blocks without backtracking. It starts from the first pending chapter and completes at the requested endpoint.
14. A fresh `--start-at qa --stop-after qa` run requires complete, gap-free translations and a current full crawl checkpoint, blocks without translating missing chapters, and can reuse a current QA checkpoint without rewriting the report. A fresh `--start-at export --stop-after export` run uses current prerequisite gates without `agy` or earlier phase invocations; stale QA or crawl evidence blocks.
15. A paused or crashed run resumes at its saved node and endpoint. `--resume` with a new phase selector is rejected. A new run from another phase works from workspace evidence even if no prior SQLite thread exists; starting it supersedes an older paused run and prevents stale resume. `auto` stops at a satisfied `--stop-after` endpoint without running later phases.
16. A crash after canonical translation write, after glossary merge, or after `state.yaml` update is recovered from the promotion journal without duplicate glossary changes or an unverified overwrite. A valid completed chapter is never retranslated. Missing or hash-invalid predecessor translation blocks even when its state says completed.
17. `--agy-model` applies to all agent calls, including chapter translation when there is no override; `--agy-translation-model` overrides it only for chapter translation. Explicit selections remain pinned on resume. A QA-only or export-only run requires no model check or agent executable. Logs distinguish requested from CLI-reported effective model.

### 10.1 Test method and phase-entry matrix

Use a small initialized workspace fixture with real catalog/state/report/approval hashes and a scripted `MockRunner`; never make an LLM or live-site call in unit/integration tests. Inject failures at process and domain-write boundaries. For each case assert the final `OperationResult`, CLI exit code, selected node/CLI call sequence, gate hashes, promoted chapter IDs, run/thread ID, and that no disallowed phase or agent call occurred. Parameterize both `--auto-approve` and manual approval where the gate can pause. Cover all ten valid explicit `start_at`/`stop_after` pairs in phase order, all six reversed pairs as invalid, and all four `auto` endpoints; the rows below name cases needing distinct evidence or assertions. The real Antigravity and live-site smoke checks in item 12 are separate, opt-in tests on a disposable two-chapter workspace.

| ID | Starting evidence and invocation | Required result and forbidden work |
| --- | --- | --- |
| E01 | New empty catalog; `--start-at auto --stop-after export` | Discover/download, full crawl gate, ordered chapter translation, QA gate, export; no gate approval before valid evidence. |
| E02 | New empty catalog; `crawl/crawl` | Discover and download, then complete only after full crawl approval; no metadata/translation/QA/export call. |
| E03 | Complete current crawl gate; `crawl/crawl` | Complete as a no-op; no crawler, agent, or report rewrite. |
| E04 | Nonempty catalog with missing or invalid raw chapters; `crawl/crawl` | Reuse catalog, fetch only pending/invalid chapters, report and approve full scope. |
| E05 | Current full crawl gate, translated prefix of chapters; `translate/translate` with no prior LangGraph thread | Start at first pending chapter, preserve predecessor context, finish translations; no crawl/QA/export. |
| E06 | Missing, partial, stale, or zero-chapter crawl evidence; `translate/translate` | Block with specific prerequisite; no automatic crawl or agent call. |
| E07 | All translation artifacts valid; `translate/translate` | Complete without metadata or translator invocation and without rewriting chapters. |
| E08 | Valid full crawl and all translations, no QA gate; `qa/qa` with no prior thread | Run deterministic QA and approval only; no `agy`, crawl, or translation. |
| E09 | Current QA gate; `qa/qa` | Complete without regenerating QA report or approval. |
| E10 | Translation gap, missing/hash-invalid translation, or stale crawl evidence; `qa/qa` | Block before QA and without invoking a translator. |
| E11 | Current crawl and QA gates, complete translations; `export/export` with no prior thread | Regenerate requested formats only; no `agy` or prior phases. |
| E12 | Missing/stale QA gate, incomplete translations, or stale crawl gate; `export/export` | Block with the earliest failed prerequisite; no export or backtracking. |
| E13 | `auto` with each `--stop-after` endpoint already satisfied | Complete at that endpoint without running later phases; `export` regeneration remains opt-in through explicit `--start-at export`. |
| E14 | Explicit completed start phase with a later endpoint | Skip the completed phase and continue only through the selected later phases. |
| E15 | `--stop-after` earlier than explicit `--start-at`, unknown phase, conflicting `--resume` options, or decision without pending approval | Reject before creating side effects or a new run. |

### 10.2 Resume, failure, and lifecycle matrix

| ID | Injected state or interruption | Required result |
| --- | --- | --- |
| R01 | Manual crawl approval pauses; resume with unchanged evidence and `approve` | Same run/thread ID, one approval write, later selected phases continue. |
| R02 | Manual QA approval pauses; resume with unchanged evidence and `approve` | Same run/thread ID, one QA approval write, export runs only if selected. |
| R03 | Report, raw/catalog, translation, or state evidence changes while approval is paused | Saved decision cannot approve stale evidence; regenerate report and require a new decision. |
| R04 | Resume a paused approval with `reject`, with no decision, or with a second decision after terminal status | Reject ends blocked; missing decision is reported as still paused without graph advancement; terminal decision cannot be replayed. |
| R05 | Crash after crawl or QA approval write but before graph checkpoint | Gate is rechecked; no duplicate approval or report rewrite. |
| R06 | Kill crawl after a subset of raw files completes | `--resume` on the same run reuses valid files and catalog, downloads remaining work, and respects original phase span. |
| R07 | Kill translator before staging, after staging, or during timeout cleanup | No stale staged output is promoted; attempt journal retains count; retry starts from the same pending chapter after process-tree shutdown. |
| R08 | Crash after each promotion replacement: canonical text, glossary/conflict report, `state.yaml` | Promotion journal rolls forward only matching prepared hashes; one completed chapter, no duplicate glossary merge or retranslation. Divergent files block. |
| R09 | Three failed translator launches with an intervening crash/resume | Same-run budget is exhausted exactly once; later chapter is never started. A new explicit run gets its own budget and rechecks workspace evidence. |
| R10 | Paused run followed by explicit new `--start-at` | Old run becomes `superseded`, cannot resume; new run uses current workspace evidence and a new thread ID. |
| R11 | Second orchestrator process targets a locked workspace | Second process blocks without child process or file mutation; lock release on pause/exit and reacquisition on resume are tested. |
| R12 | Valid prior workspace gate exists but SQLite file or earlier run history is absent | New direct `translate`, `qa`, or `export` run succeeds from workspace evidence; `--resume` without a run ID reports a clear error. |
| R13 | Crash after metadata update but before graph checkpoint | Resume sees valid translated metadata and does not invoke the metadata agent twice. |
| R14 | Crash after QA report write but before approval, or after QA approval before export | Resume rechecks report/evidence and obtains a fresh manual decision if needed; a current QA gate is reused without report rewrite. |
| R15 | Crash after one requested export artifact is written | Resume rechecks QA and verifies or regenerates each requested format; no crawl, translation, or QA rerun, and completion requires all requested outputs. |

### 10.3 Contract and guidance tests

| ID | Contract | Required assertion |
| --- | --- | --- |
| C01 | Model routing | Global model reaches profile repair, metadata, and translator; translation override affects only translator. Invalid slug fails before agent launch; explicit choices persist on resume. |
| C02 | Agent output authority | Exit code 0 or success JSON without valid staged artifact cannot advance. An unexpected edit to protected workspace files blocks. |
| C03 | Domain blockers | Missing predecessor, chapter gap, stale gate, zero discovered chapters, failed profile probe, QA error, and missing required export dependency stop at their own phase without an agent retry loop. |
| C04 | Harness guidance | Generated `AGENTS.md` and `CLAUDE.md` include development and operations sections; every panel points to the same orchestrator CLI and declares Antigravity as the initial agent backend. Cowork uses its supported CLI environment form. |
| C05 | Skill mapping | All four prefixed phase skills for all harnesses invoke only their mapped `--start-at/--stop-after` span; the new prefixed `orchestrate-book` skill supports arbitrary valid spans and resume. None contains direct approval, promotion, coordinator, or native translator dispatch instructions. |
| C06 | Generated tree | Manifest, generator output, `opencode.json` policy, skill frontmatter/discovery, and generated guides agree. `sync_harness_adapters.py --check` fails on missing/stale current outputs **and** obsolete generated adapters, then passes after regeneration and targeted cleanup. |
| C07 | Agent definitions | Among generated pipeline agent definitions, only the Antigravity translator and metadata translator needed by the initial runner remain discoverable; retired coordinator, inactive harness translator agents, old dispatch fragments, and Claude translation workflow cannot be selected accidentally. |
| C08 | Logs and exit contract | Completed/paused/blocked/error use the documented exit codes; run summary records phase, chapter attempt, requested/reported model, and paths without raw or full translated chapter text. |

Run tests and quality checks with `PYTHONUTF8=1` and workspace-local `UV_CACHE_DIR` on Windows.
