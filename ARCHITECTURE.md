# Dich Truyen Agent Architecture

This document describes the internal workflow logic for Dich Truyen Agent:
workspace artifacts, pipeline gates, glossary consistency, subagent isolation,
and generated harness adapters.

For setup and everyday usage, see [README.md](README.md).

---

## Architecture Versioning

This document describes **Translation Orchestration Architecture v2.2**.

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
- **v2.2 - genre-aware style profiles + emotional craft:** the translation
  style system is extended with genre-specific profiles and universal emotional
  craft guidance. `init-book` now accepts `--style <profile-name>` and defaults
  to `general` instead of `tien_hiep`. The translator prompt is rewritten to
  require emotional fidelity, prose rhythm, and natural dialogue voice, and the
  harmful ASCII diacritic-stripping rule is removed.

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
uv run python main.py init-book --slug <book-slug> --title "<title>" --source-url "<source-url>" --style <profile-name>
```

The `--style` flag accepts either a bare profile name (`general`, `tien_hiep`,
`mat_the`, `do_thi`) or an explicit path to a custom YAML file. It defaults to
`general` when omitted. The agent infers the book's genre before initialization
and recommends the most appropriate profile; the user confirms or overrides
before `init-book` runs. See the shared main-agent guide for the recommendation
flow.

Important outputs:

- `book.yaml`: source URL, original title, author, and translated metadata.
- `chapters.yaml`: chapter catalog once crawling discovers chapters.
- `state.yaml`: per-chapter raw and translation stage status.
- `style.yaml`: local style guide snapshot copied into the workspace.

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

## Translation Style System

Translation quality is controlled through two independent layers that are set at
init time and remain fixed for the lifetime of the workspace.

### Layer 1 — Register (per-genre)

The `style.yaml` workspace snapshot carries a genre-specific **register**: the
tonal dialect for the book (archaic-formal, modern-colloquial, etc.). The
translator subagent reads this from `style_path` and applies it throughout the
chapter.

Bundled genre profiles live in `templates/styles/`:

| Profile name | File | Genre |
| --- | --- | --- |
| `general` | `general.yaml` | Neutral fallback — used when genre is unclear |
| `mat_the` | `mat_the.yaml` | Modern apocalypse / zombie survival |
| `do_thi` | `do_thi.yaml` | Modern urban / contemporary city life |
| `tien_hiep` | `tien_hiep.yaml` | Xianxia / cultivation / wuxia |

Each profile declares:

- `name`, `description`, `tone` — identity fields.
- `guidelines` — prose-level rules specific to this genre.
- `vocabulary` — Chinese-to-Vietnamese term overrides.
- `examples` — sample passages showing expected output.
- `register` — tonal register label (e.g. `hiện đại, đời thường, căng thẳng sinh tồn`).
- `emotion_guidelines`, `voice_guidelines`, `rhythm_guidelines` — craft rules
  for emotion, character voice, and sentence rhythm that the translator must
  apply.

Custom profiles can be provided at any path and passed to `--style` as an
explicit file path.

`TranslationStyle` in `models.py` is the Pydantic model for these files. All
craft fields are optional with empty defaults, so workspace snapshots from
before v2.2 still load without errors.

### Layer 2 — Craft (universal)

The translator prompt (`.harness/source/agents/translator.md`) carries universal
craft rules that apply to every book regardless of genre:

- **Emotional fidelity:** convey each character's felt experience using verbs
  and adjectives that carry emotional charge; do not flatten to neutral narration.
- **Prose rhythm:** vary sentence length and cadence — short clipped sentences
  in action, longer flowing sentences in reflection; avoid uniform cadence.
- **Natural dialogue voice:** render speech as a Vietnamese speaker would
  naturally say it; give characters distinct voices.
- **Show, don't report:** prefer concrete, sensory phrasing over flat
  descriptive narration.

The prompt also mandates a self-review step that checks diacritics, register
match, and craft application before the chapter is written to the staging file.
No ASCII diacritic stripping is performed; all Vietnamese output must carry full
diacritics.

### Style resolution

`src/dich_truyen_agent/styles.py` exposes `resolve_style_path()` with three modes:

1. `--style` omitted → `templates/styles/general.yaml`.
2. `--style <bare-name>` → `templates/styles/<bare-name>.yaml`.
3. `--style <path>` where the path exists → used as-is.

An unrecognized bare name raises a `ValueError` with a clear message rather than
silently producing a missing-file path.

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

### ADR-0003: Genre-Aware Style Profiles and Emotional Craft

- **Status:** Accepted
- **Date:** 2026-06-15
- **Architecture version:** v2.2

#### Context

Translation output for `mo-ri-zhang-lang` (a modern zombie-survival novel) was
machine-like: characters' fear, panic, and banter did not come through, and
sentence rhythm was uniform regardless of scene pacing. Review identified two
root causes:

1. The translator prompt contained no guidance on emotional fidelity, prose
   rhythm, or character voice — it optimized for "professional, elegant, archaic"
   correctness only.
2. The style system had a single profile (`tien_hiep.yaml`), hardcoded as the
   default for every book. A zombie-apocalypse novel was being translated in
   archaic xianxia register, producing phrases like `"tại hạ xin cáo từ"` and
   `"thiên linh cái"` mid zombie-chase.

A secondary defect in the translator prompt — a "Lexical Sandbox Rule" with an
ASCII replacement table — was stripping Vietnamese diacritics and producing
output like `"Ngoi... la... ngoi... phuong... nao...?"` instead of fully
accented Vietnamese.

#### Decision

Separate **craft** (universal, every book) from **register** (per-genre,
per-book):

**Craft layer (translator prompt):** Rewrite Steps 4–5 and the self-review
checklist in `.harness/source/agents/translator.md` to mandate:

- Emotional fidelity — translate the character's felt experience, not just the
  literal words.
- Prose rhythm — vary sentence length and cadence to match scene pacing.
- Natural dialogue voice — render speech as a Vietnamese speaker would say it.
- Show, don't report — prefer concrete, sensory phrasing.
- Remove the ASCII diacritic-stripping rule; require fully-accented Vietnamese
  in all output.

**Register layer (style profiles):** Extend `TranslationStyle` with optional
fields `register`, `emotion_guidelines`, `voice_guidelines`, and
`rhythm_guidelines`. Provide four bundled profiles in `templates/styles/`:
`general` (neutral fallback), `mat_the` (apocalypse/survival), `do_thi`
(modern urban), and enrich `tien_hiep` with the new craft fields.

**Init flow:** Change the `--style` default from `tien_hiep` to `general`.
Add bare-profile-name resolution to `resolve_style_path()`. Document a
genre-recommendation step in the shared main-agent guide so the agent infers
genre and proposes a profile before `init-book` runs.

#### Consequences

- Future translations for any genre receive both correct register and explicit
  emotional-craft guidance.
- The wrong-register problem is eliminated for new books; existing workspace
  snapshots still load because all new `TranslationStyle` fields are optional
  with empty defaults.
- The diacritic-stripping defect is gone; the self-review checklist now verifies
  full diacritics explicitly.
- The `general` default prevents any book from silently receiving archaic
  xianxia styling.
- Translator isolation, sequential ordering, staging, promotion, and glossary
  gates are unchanged.
- A second "literary editor" refine pass was considered (Approach C) and
  rejected: it would double per-chapter cost, break the single-subagent-per-
  chapter contract, and add non-deterministic context coupling between passes.

#### Verification

- `TranslationStyle` loads with and without the new fields (backward compat).
- Each bundled profile passes `validate-style`.
- `load_selected_style` resolves bare profile names, explicit paths, and the
  `general` default.
- Translator prompt assertions: `"Emotional fidelity"`, `"Prose rhythm"`,
  `"dialogue voice"`, `"register"` present; `"Lexical Sandbox"` absent;
  `"diacritic"` present.
- Genre-recommendation section in shared guide: `"--style"`, `"genre"`,
  `"mat_the"`, `"recommend"` present.
- Generated adapters verified in sync via `sync_harness_adapters.py --check`.
- Full test suite: 311 passed, 1 skipped.
