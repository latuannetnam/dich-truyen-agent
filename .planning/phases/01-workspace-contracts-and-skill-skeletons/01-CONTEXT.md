# Phase 1: Workspace Contracts and Skill Skeletons - Context

**Gathered:** 2026-05-31
**Status:** Ready for planning

<domain>
## Phase Boundary

Establish the inspectable local filesystem foundation shared by every later workflow: new-book
workspace initialization, validated contracts for immutable and mutable book data, atomic file
replacement, explicit resume behavior, hash-backed approval gates, workspace-local translation
style snapshots, and thin project-local skill entrypoint contracts. Crawling, glossary
generation, translation, QA analysis, and ebook export remain later-phase capabilities.

</domain>

<decisions>
## Implementation Decisions

### Book Workspace Layout
- **D-01:** Initialize books under `books/<book-slug>/`.
- **D-02:** Use stage-oriented folders: `raw/`, `translations/`, `staging/`, `reports/`,
  `checkpoints/`, and `exports/`.
- **D-03:** Keep immutable chapter catalog facts in `chapters.yaml` and mutable processing
  progress in `state.yaml`.
- **D-04:** Name raw and translated chapter files with stable numeric IDs plus readable slugs,
  such as `0001-chuong-mo-dau.txt`.

### Initialization and Resume Rules
- **D-05:** Initialization must refuse an existing `books/<book-slug>/` directory unless the
  user explicitly requests resume.
- **D-06:** Resume must validate files already marked complete and preserve them when valid.
- **D-07:** Interrupted atomic writes must leave the last valid canonical file in place. Orphan
  temporary files are ignored and reported, not promoted or deleted automatically.
- **D-08:** If completed state conflicts with a missing or invalid canonical file, stop with an
  actionable error and require explicit repair or reset. Do not silently reprocess work.

### Approval Checkpoint Records
- **D-09:** Store approvals as structured YAML records containing checkpoint type, approval
  timestamp, relevant report path, and evidence hashes of reviewed inputs.
- **D-10:** Any change to reviewed inputs invalidates the corresponding checkpoint and blocks
  the gated step until the user reviews and approves the updated inputs.
- **D-11:** Gate failures return compact actionable metadata: missing or stale checkpoint type,
  reason, and relevant report and approval paths.
- **D-12:** Create checkpoints only through an explicit approval helper command after user
  review.

### Style and Skill Contracts
- **D-13:** Copy the selected translation style into each book workspace as `style.yaml` so
  resumes use the same reviewed configuration.
- **D-14:** Ship the bundled default as `templates/styles/tien_hiep.yaml`; initialization copies
  it into the workspace.
- **D-15:** Phase-1 skill skeletons are thin documented entrypoints. They define expected
  arguments, workspace paths, helper boundaries, and clear unfinished-step failures without
  implementing later-phase workflows.
- **D-16:** Helpers write validated compact result files and print concise terminal summaries
  with status, reason, progress, and report paths. Avoid returning verbose logs or chapter
  content through the agent context.

### the agent's Discretion
No implementation decisions were delegated during discussion.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Scope and Requirements
- `.planning/PROJECT.md` - Defines the agent-native workflow, v1 constraints, checkpoints, and
  out-of-scope capabilities.
- `.planning/REQUIREMENTS.md` - Defines phase-1 requirements `WORK-01` through `WORK-04`,
  `STYL-01`, and `STYL-02`.
- `.planning/ROADMAP.md` - Defines the fixed phase boundary, success criteria, and planned split
  between `01-01` and `01-02`.

### Stack Guidance
- `.planning/research/STACK.md` - Defines Python 3.13, `uv`, Pydantic boundary validation,
  PyYAML safe loading, atomic replacement guidance, and Codex skill entrypoints.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `pyproject.toml`, `.python-version`, and `uv.lock`: existing Python 3.13 `uv` scaffold for the
  new helper package and dependencies.
- No reusable package modules exist yet; phase 1 establishes the initial package structure.

### Established Patterns
- The repository is intentionally minimal. Persisted workspace boundaries should introduce
  Pydantic models and YAML serialization as the first stable conventions.
- User-facing orchestration belongs in project-local Codex skills; deterministic filesystem
  behavior belongs in small Python helpers.

### Integration Points
- Add the helper package and tests around the existing `pyproject.toml`.
- Add reusable style templates under `templates/styles/`.
- Add thin project-local skill entrypoints without crossing into later-phase behavior.

</code_context>

<specifics>
## Specific Ideas

- Prefer easily browsed local files and stage-oriented folders over opaque internal state.
- Preserve diagnostic evidence from interrupted writes by reporting orphan temporary files
  rather than deleting them automatically.

</specifics>

<deferred>
## Deferred Ideas

None - discussion stayed within phase scope.

</deferred>

---

*Phase: 1-workspace-contracts-and-skill-skeletons*
*Context gathered: 2026-05-31*
