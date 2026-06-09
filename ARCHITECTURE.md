# Dich Truyen Agent Architecture

This document describes the internal workflow logic for Dich Truyen Agent:
workspace artifacts, pipeline gates, glossary consistency, subagent isolation,
and generated harness adapters.

For setup and everyday usage, see [README.md](README.md).

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

### 3. Prepare Translation Context

Before each chapter is translated, the coordinator calls:

```powershell
$env:PYTHONUTF8=1
uv run python main.py prepare-translation-context --workspace books/<book-slug> --chapter-id <chapter_id>
```

This command enforces the crawl gate and strict sequential order. Chapter `N`
cannot be prepared until every earlier chapter is promoted.

It returns compact paths for the translator subagent:

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

The active harness translate skill runs a bounded loop. The main agent checks
progress, then delegates batches to a coordinator where supported. The
coordinator spawns one translator subagent per chapter.

The translator subagent is the only worker that reads raw Chinese chapter files.
It reads only the paths supplied by `prepare-translation-context`, then writes:

- `staging/chuong-NNNN-staged.txt`: Vietnamese draft.
- `staging/chuong-NNNN-proposals.yaml`: optional new glossary proposals.

The main agent and coordinator avoid bulk-reading raw or translated chapter
contents to protect the context window.

### 5. Promote Chapter Output

After staging, the coordinator runs:

```powershell
$env:PYTHONUTF8=1
uv run python main.py promote-chapter --workspace books/<book-slug> --chapter-id <chapter_id>
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
