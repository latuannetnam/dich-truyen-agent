# Dich Truyen Agent Architecture

This document describes the internal workflow logic for Dich Truyen Agent:
workspace artifacts, pipeline gates, glossary consistency, subagent isolation,
and generated harness adapters.

For setup and everyday usage, see [README.md](README.md).

---

## Architecture Versioning

This document describes **Translation Orchestration Architecture v2.1**.

Architecture changes are versioned when they alter durable workspace contracts,
CLI orchestration contracts, generated harness behavior, or recovery semantics.
Documentation-only clarifications do not create a new architecture version.

Current versions:

- **v1 - gated sequential pipeline:** crawl approval, sequential translation,
  per-chapter promotion, glossary consistency, QA approval, and export gates.
- **v2 - compact shared orchestration:** all harnesses use a shared 5-chapter
  batch contract, deterministic JSON CLI work items, structural staging
  verification through the CLI, and compact coordinator summaries for 1000+
  chapter books.
- **v2.1 - configurable compact batch size:** the compact orchestration batch
  size defaults to 5 but can be configured from project `.env` with
  `DICH_TRUYEN_TRANSLATION_BATCH_SIZE`.

Versioned changes must update:

- `ARCHITECTURE.md`, including an ADR entry for the decision.
- `.harness/source/**` when generated harness behavior changes.
- Generated adapters via `tools/sync_harness_adapters.py`.
- Tests that prove CLI contracts, generated adapter sync, and compatibility
  with existing quality gates.

---

## Workspace Structure

A book workspace is managed under `books/<book-slug>/`:

```text
books/<book-slug>/
├── book.yaml               # Immutable book metadata and translated metadata
├── chapters.yaml           # Chapter catalog mapping IDs to files and URLs
├── state.yaml              # Active raw and translation stage records
├── style.yaml              # Local translation style guide snapshot
├── glossary.yaml           # Chinese to Vietnamese terminology glossary
├── raw/                    # Downloaded Chinese raw text files
├── translations/           # Promoted Vietnamese translation files
├── staging/                # Staged drafts, glossary contexts, proposals
├── checkpoints/            # Cryptographic approvals
├── exports/                # Exported ebook files
└── reports/
    ├── crawl.yaml          # Crawler verification statistics
    ├── qa-report.yaml      # Translation QA findings
    ├── glossary-conflicts.yaml # Glossary merge conflict log
    └── results/            # Persisted CLI execution result metadata
```

`state.yaml` is the source of truth for completed raw and translation stages.
The actual file hashes are stored in state and checkpoint records, so manual
file changes invalidate the affected gate or completed stage.

---

## End-To-End Pipeline Logic

The pipeline is a gated local workflow. Each phase writes deterministic
workspace artifacts, and later phases refuse to run until required earlier
evidence has been approved.

### 1. Initialize Book Workspace

`init-book` creates the book directory, writes the metadata snapshot, installs
the selected style, and initializes empty chapter and state records:

```powershell
$env:PYTHONUTF8=1
uv run python main.py init-book --slug <book-slug> --title "<title>" --source-url "<source-url>"
```

Important outputs:

- `book.yaml`: source URL, original title, author, and translated metadata.
- `chapters.yaml`: chapter catalog once crawling discovers chapters.
- `state.yaml`: per-chapter raw and translation stage status.
- `style.yaml`: local style guide copied into the workspace.

### 2. Crawl Raw Chinese Chapters

The active harness crawl skill runs the crawler through the CLI. The crawler
discovers chapter URLs, downloads raw Chinese text, writes files under `raw/`,
updates `chapters.yaml` and `state.yaml`, and creates `reports/crawl.yaml`.

The crawl output is not trusted automatically. The user or operator reviews the
crawl evidence and approves it:

```powershell
$env:PYTHONUTF8=1
uv run python main.py approve-crawl --workspace books/<book-slug>
```

This creates `checkpoints/crawl-approved.yaml`. Translation is blocked until
that checkpoint is valid.

### 3. Prepare Translation Work Item

Before each chapter is translated, the coordinator calls the compact shared
work-item command:

```powershell
$env:PYTHONUTF8=1
uv run python main.py next-translation-work-item --workspace books/<book-slug> --json
```

This command combines progress discovery and translation context preparation
into a deterministic JSON `OperationResult.data` payload. It enforces the crawl
gate, detects completed workspaces, reports blocked state gaps, prepares the
chapter glossary context, and returns absolute paths for the translator.

The lower-level context command remains available:

```powershell
$env:PYTHONUTF8=1
uv run python main.py prepare-translation-context --workspace books/<book-slug> --chapter-id <chapter_id>
```

Both commands enforce strict sequential order. Chapter `N` cannot be prepared
until every earlier chapter is promoted.

The work-item payload returns compact orchestration data only:

- `state`: `pending`, `completed`, `blocked`, or `error`.
- `progress_completed` and `progress_total`.
- `chapter_id`, `slug`, and `original_title` for pending work.
- `raw_path`, `style_path`, `glossary_path`, `glossary_context_path`.
- `prev_translation_path`, or `null` for chapter 1.
- `staged_txt` and `staged_yaml`.
- staging existence and fallback metadata.

It must never include raw Chinese text, completed Vietnamese chapter bodies, or
cumulative chapter lists.

The translator subagent receives these paths:

- `raw_path`: the raw Chinese chapter file.
- `style_path`: the workspace style guide.
- `glossary_path`: the full book glossary.
- `glossary_context_path`: a chapter-specific glossary context file.
- `prev_translation_path`: the promoted Vietnamese chapter `N-1`, or `null` for chapter 1.

The generated `staging/chuong-NNNN-glossary-context.yaml` file narrows the full
glossary down to terms found in the current raw chapter and includes rejected
aliases from unresolved glossary conflicts. It helps the translator use
canonical names and avoid known bad variants.

### 4. Translate Sequentially With Isolated Subagents

The active harness translate skill runs a compact bounded loop. All harnesses
share the same effective batch size. The default is **5 chapters per
coordinator/workflow batch**, and project `.env` can override it:

```env
DICH_TRUYEN_TRANSLATION_BATCH_SIZE=10
```

Runtime arguments, such as a workflow `max_chapters` override, take precedence
over `.env`; `.env` takes precedence over the built-in default. Invalid values
fail through `show-translation-settings` instead of silently falling back.

For long books, including 1000+ chapter books, full automation is achieved by
repeatedly starting fresh compact batches and re-querying CLI state after each
batch.

The main agent checks compact work-item state, then delegates batches to a
coordinator where supported. The coordinator spawns one translator subagent per
chapter.

The translator subagent is the only worker that reads raw Chinese chapter files.
It reads only the paths supplied by `next-translation-work-item`, then writes:

- `staging/chuong-NNNN-staged.txt`: Vietnamese draft.
- `staging/chuong-NNNN-proposals.yaml`: optional new glossary proposals.

The main agent and coordinator avoid reading raw, staged, or translated chapter
contents. Coordinators return only compact batch summaries:

```json
{
  "status": "ok|completed|blocked|error",
  "processed_count": 0,
  "chapter_start": null,
  "chapter_end": null,
  "next_chapter_id": null,
  "failure_reason": null
}
```

This prevents main-agent context growth from cumulative per-chapter logs while
preserving resumability through `state.yaml`.

### 5. Promote Chapter Output

After staging, the coordinator first runs structural verification:

```powershell
$env:PYTHONUTF8=1
uv run python main.py verify-staged-chapter --workspace books/<book-slug> --chapter-id <chapter_id> --json
```

This verifies only the staged file shape, such as header format and required
blank separator. It does not check glossary quality and does not replace
promotion.

Then the coordinator runs promotion:

```powershell
$env:PYTHONUTF8=1
uv run python main.py promote-chapter --workspace books/<book-slug> --chapter-id <chapter_id> --json
```

Promotion validates the staged text, checks glossary consistency, merges valid
new glossary proposals, writes the final chapter under `translations/`, updates
`state.yaml`, and removes the staged draft files.

Promotion is blocked if:

- The staged text is missing, empty, or malformed.
- The proposal file is invalid YAML.
- A proposed glossary mapping conflicts with an existing glossary term.
- The staged translation uses a rejected glossary alias for a relevant term.

When promotion blocks, staged files remain in place so the same chapter can be
retried or inspected. Completed chapters remain clean up to the last successful
promotion.

### 6. Quality Assurance Gate

After translation, the QA skill runs:

```powershell
$env:PYTHONUTF8=1
uv run python main.py check-translation --workspace books/<book-slug>
```

QA writes `reports/qa-report.yaml` and checks structural completeness, missing
or empty translations, Chinese residue, punctuation anomalies, abnormal raw to
Vietnamese length ratios, unresolved glossary conflicts, and rejected glossary
alias usage.

The user approves QA only after reviewing the report:

```powershell
$env:PYTHONUTF8=1
uv run python main.py approve-qa --workspace books/<book-slug>
```

This creates `checkpoints/qa-approved.yaml`. Export is blocked until that
checkpoint is valid.

### 7. Export Ebooks

The export phase validates the QA checkpoint, compiles the canonical EPUB 3.3
book from `translations/`, runs EPUBCheck when configured, and optionally derives
Calibre formats:

```powershell
$env:PYTHONUTF8=1
uv run python main.py export-book --workspace books/<book-slug> --formats epub,azw3,mobi,pdf
```

Exports are written under `exports/`. Because checkpoint approvals include
evidence hashes, changing approved reports or translation files invalidates the
gate and forces review again.

### Failure And Resume Behavior

The pipeline is resumable by design. Each phase writes atomically, stores compact
result metadata under `reports/results/`, and keeps `state.yaml` as the source of
truth for completed raw and translation stages. If translation stops, rerunning
the harness translate skill resumes from the first pending chapter.

For long books, the main agent must not remember which chapters were promoted
across batches. It must call `next-translation-work-item` again and trust the
workspace state.

---

## Glossary Lifecycle

After crawl approval, the agent initializes and evolves `glossary.yaml` as
translation proceeds. Users can edit names or terms directly in the glossary or
ask the agent to lock canonical translations for important terms.

During translation, `prepare-translation-context` writes a bounded
`staging/chuong-NNNN-glossary-context.yaml` file for the next chapter. It lists
glossary terms found in that raw chapter and any rejected aliases from unresolved
conflict records.

`promote-chapter` blocks before writing to `translations/` if the staged draft
proposes a conflicting mapping or uses a rejected alias. QA also treats
unresolved glossary conflicts as blocking findings.

---

## Harness Adapter Architecture

The workspace is operated through generated harness adapters rather than one
runtime-specific skill set. The shared architecture keeps one canonical source
of truth while still allowing each coding-agent runtime to use its native tools
for commands, bounded file reads, and subagent delegation.

- Canonical source lives in `.harness/source/`.
- Generated runtime adapters are committed so every harness can discover them
  without running setup first.
- Adapter names are prefixed to avoid duplicate or ambiguous discovery:
  `ag-*` for Antigravity, `cc-*` for Claude Code, `oc-*` for OpenCode, and
  `codex-*` for Codex.
- Root guide files are generated from shared main-agent logic:
  `AGENTS.md` contains the cross-harness guide and `CLAUDE.md` contains the
  Claude-specific panel.
- OpenCode duplicate-discovery protection is declared in `opencode.json`; only
  the `oc-*` pipeline skills remain active for OpenCode.
- Translation orchestration is shared across harnesses through
  `next-translation-work-item`, `verify-staged-chapter`, and JSON promotion
  through `promote-chapter --json`; harness-specific code only controls native
  subagent dispatch.

Generated adapter locations:

```text
.agent/skills/ag-*          # Antigravity skills
.agent/agents/ag_*          # Antigravity subagents
.claude/skills/cc-*         # Claude Code skills
.claude/agents/cc_*         # Claude Code subagents
.opencode/skill/oc-*        # OpenCode skills
.opencode/agent/oc-*        # OpenCode subagents
.codex/skills/codex-*       # Codex skills
.codex/agents/codex_*       # Codex subagents
```

Do not edit generated adapter files directly. Update `.harness/source/**`, then
regenerate and verify:

```powershell
$env:PYTHONUTF8=1
uv run python tools/sync_harness_adapters.py
uv run python tools/sync_harness_adapters.py --check
uv run pytest -q
uv run ruff check tools tests src main.py
```

Generated files include a `GENERATED from .harness/source` header. If a generated
file is stale, `tools/sync_harness_adapters.py --check` reports it.

---

## Architecture Decision Records

### ADR-0001: Shared Compact Translation Orchestration

- **Status:** Accepted
- **Date:** 2026-06-12
- **Architecture version:** v2

#### Context

The original translation loop delegated larger coordinator batches and required
harness instructions to parse progress and context separately. That worked for
short and medium books, but 1000+ chapter books risked main-agent context growth
from repeated per-chapter summaries and long-running coordinator state.

Codex exposed the pressure most clearly, but the underlying issue was not
Codex-specific. The repository has a multi-harness architecture, so fixing only
one adapter would create divergent behavior and harder recovery semantics.

The glossary quality gate already lived in `promote-chapter`, where staged
proposals and rejected aliases are checked before writing final translations.
Any orchestration redesign needed to preserve that promotion-bound gate.

#### Decision

Use one shared compact orchestration contract for every harness:

- Batch size is **5 chapters** for all harnesses.
- `next-translation-work-item --json` is the canonical work discovery and
  context path command.
- `verify-staged-chapter --json` performs structural staged-output checks only.
- `promote-chapter --json` remains mandatory after each staged chapter and
  preserves the glossary consistency gate.
- Coordinators return compact batch summaries only:
  `{status, processed_count, chapter_start, chapter_end, next_chapter_id,
  failure_reason}`.
- The main agent re-queries CLI state after each batch instead of accumulating
  promoted chapter arrays.

#### Consequences

- 1000+ chapter books can run through full automation using many fresh compact
  batches while keeping each coordinator context bounded.
- Main-agent memory growth is proportional to compact batch summaries, not raw
  chapter contents or cumulative chapter lists.
- Resume behavior remains deterministic because `state.yaml`, promoted file
  hashes, and checkpoints remain the source of truth.
- All harnesses share the same orchestration semantics; runtime-specific
  adapters only differ in native subagent dispatch.
- Promotion remains the only point that merges glossary proposals and writes
  canonical translations, so per-chapter glossary quality is not weakened.

#### Verification

The v2 contract is covered by tests for:

- compact pending/completed/blocked work-item payloads;
- structural staged verification;
- 1000+ chapter catalog compactness;
- generated harness adapter sync and shared batch-size wording;
- existing promotion blockers for conflicting glossary proposals and rejected
  aliases.

### ADR-0002: Configurable Compact Batch Size

- **Status:** Accepted
- **Date:** 2026-06-12
- **Architecture version:** v2.1

#### Context

The compact orchestration contract originally fixed the batch size at 5 for all
harnesses. That default is safe for 1000+ chapter books, but some workspaces and
models can tolerate larger batches, while constrained runs may need smaller
batches.

The repository already supports environment-based local configuration for
export tooling, and `.env` is ignored by git. The batch-size setting should
remain shared across harnesses rather than becoming adapter-specific.

#### Decision

Add `DICH_TRUYEN_TRANSLATION_BATCH_SIZE` as the shared translation batch-size
setting. The effective value is resolved through `show-translation-settings
--json`.

Precedence is:

1. explicit runtime argument, such as workflow `max_chapters`;
2. `.env` or process environment;
3. built-in default of 5.

Invalid values, including `0`, negative numbers, and non-integers, fail clearly
through the settings CLI.

#### Consequences

- All harnesses continue to share one compact orchestration contract.
- Operators can tune long-book throughput locally without editing generated
  adapters.
- The default remains conservative for memory safety.
- Translator isolation, sequential ordering, structural staging verification,
  and promotion-bound glossary gates are unchanged.
