# Phase 4: Sequential Agent-Native Translation - Context

**Gathered:** 2026-06-01
**Status:** Ready for planning

<domain>
## Phase Boundary

Translate approved raw chapters sequentially using context-isolated subagents while keeping the orchestration token-efficient and failure recovery deterministic.

* **In Scope:**
  - Enforce the `crawl-approved` checkpoint before starting translation.
  - Spawn context-isolated translation subagents for each chapter sequentially.
  - Provide strict continuity context (Vietnamese translation of Chapter `N-1` if available).
  - Use a temporary staging and atomic promotion flow to prevent corrupting completed work.
  - Evolve the glossary by processing progressive chapter-level proposals.
  - Manage the sequential loop and retry safety directly within the `$translate-book` skill surface.
* **Out of Scope:**
  - Quality assurance checks and exports (Phase 5 and Phase 6).
  - Web UI or FastAPI endpoints.
  - Parallel translation of adjacent chapters.

</domain>

<decisions>
## Implementation Decisions

### D-01: Subagent Worker Invocation Model
- Spawns a context-isolated translation subagent for each chapter.
- The orchestrator passes the paths of the context files rather than embedding them directly in the orchestrator's context.
- The subagent receives the following inputs:
  1. The original Chinese chapter text.
  2. The translation style guidelines from `style.yaml`.
  3. The current vocabulary and lock-status mapping from `glossary.yaml`.
  4. The Vietnamese translation of the previous chapter (Chapter `N-1`) if available.
- The subagent outputs a translated Vietnamese text and optionally proposes new glossary terms.

### D-02: Staging, Validation, and Atomic Promotion Flow
- **Staging Contracts:**
  - Staged Translation: Written to `staging/chuong-{chapter_id:04d}-staged.txt`.
  - Staged Proposals: Written to `staging/chuong-{chapter_id:04d}-proposals.yaml` (Chinese term -> structured mapping).
- **CLI Promotion Command (`main.py promote-chapter`):**
  - **Input:** `--workspace <path> --chapter-id <id>`
  - **Validation Steps:**
    - Checks that the staged translation file exists and is not empty.
    - Inspects the translation for structural sanity (e.g. minimum character length).
    - Checks that the staged proposals are syntactically valid YAML.
  - **Atomic Promotion Steps:**
    1. Move `staging/chuong-{chapter_id:04d}-staged.txt` atomically to `translations/<canonical_filename>`.
    2. Merge glossary proposals from `staging/chuong-{chapter_id:04d}-proposals.yaml` using the existing `merge_glossary_proposals()` contract (creating automatic snapshots and conflict reports under `reports/glossary-conflicts.yaml`).
    3. Update the chapter's translation stage state in `state.yaml` to `COMPLETED` with the correct `canonical_path` and `sha256` hash.
    4. Clean up the staging files for that chapter.
  - Returns a standard `OperationResult` JSON/YAML to the console.

### D-03: Skill-Driven Loop Orchestration
- The orchestration loop is driven directly inside the `$translate-book` skill markdown.
- **Workflow Steps:**
  1. The orchestrator checks if the `crawl-approved` checkpoint is valid using `main.py check-gate --type crawl-approved`.
  2. The orchestrator inspects the `state.yaml` file (or calls a helper) to identify the next `pending` chapter.
  3. For the target chapter `N`, the orchestrator checks if all previous chapters are `COMPLETED`.
  4. The orchestrator prepares the context, spawns the subagent, validates the staged result, and calls `main.py promote-chapter`.
  5. **Retry Safety:**
    - If translation or promotion fails, the orchestrator retries up to 3 times with a polite backoff.
    - If retries are exhausted, the loop stops immediately, leaving the workspace in a clean and consistent state. The user can manually inspect `staging/` or `glossary.yaml` and resume the skill, which will pick up exactly where it failed.

### D-04: Continuity Context Depth & Fallback
- **Continuity Input:** The subagent is provided the Vietnamese translation of Chapter `N-1` to maintain pronoun and narrative continuity.
- **Fallback Strategy:**
  - If Chapter `N-1` does not exist or is empty (e.g. for Chapter 1, or after a manual reset/state modification), the orchestrator falls back to passing **no predecessor context** to the subagent, adding an explicit instruction indicating that this is the first chapter or a narrative starting point.
  - This ensures translation never blocks due to a missing previous file, while maintaining optimal quality.

</decisions>

<canonical_refs>
## Canonical References

- `.planning/PROJECT.md` - Overall system rules and key decisions.
- `.planning/REQUIREMENTS.md` - Translation requirements `TRAN-01` through `TRAN-07`.
- `.planning/ROADMAP.md` - Success criteria and plans for Phase 4.
- `src/dich_truyen_agent/models.py` - Core state and staging models.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `check_gate()` in `src/dich_truyen_agent/checkpoints.py` to enforce gates.
- `merge_glossary_proposals()` in `src/dich_truyen_agent/glossary.py` to handle progressive merges.
- `load_yaml_model()` and `atomic_write_yaml()` in `src/dich_truyen_agent/storage.py` for atomic updates.
- `workspace_paths()` in `src/dich_truyen_agent/paths.py` for canonical workspace paths.

### Integration Points
- Update CLI in `src/dich_truyen_agent/cli.py` to register staging, context building, and promotion subcommands.
- Implement `src/dich_truyen_agent/translate_worker.py` (or integrated helpers) to assist context setup and result packaging.

</code_context>

<specifics>
## Specific Ideas

- **Context Preparation Command:** Implement a subcommand `main.py prepare-translation-context` that outputs a JSON summary of the file paths for raw chapter `N`, predecessor translation `N-1` (or fallback indicator), style `style.yaml`, and glossary `glossary.yaml`.
- **Subagent prompt:** Provide a clean markdown system prompt within the subagent boundary to enforce standard Sino-Vietnamese translation conventions, dictionary lookup, and tone directives.

</specifics>

<deferred>
## Deferred Ideas

- Target re-translation of specific chapters (deferred to Phase 5 / QA or v2).
- Automatic character description extraction from chapter text (deferred to v2).

</deferred>

---

*Phase: 4-sequential-agent-native-translation*
*Context gathered: 2026-06-01*
