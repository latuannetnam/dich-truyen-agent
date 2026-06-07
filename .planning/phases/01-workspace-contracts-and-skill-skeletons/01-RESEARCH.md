# Phase 1: Workspace Contracts and Skill Skeletons - Research

**Researched:** 2026-05-31
**Domain:** Local filesystem contracts, atomic persistence, approval checkpoints, and Codex skill entrypoints
**Confidence:** HIGH

## Summary

Phase 1 should create a small `src/dich_truyen_agent/` package whose only job is to make later
workflow stages predictable. The package should own validated YAML boundaries, deterministic
workspace paths, atomic file replacement, resume validation, hash-backed approval records,
style snapshots, and compact CLI-facing result models. Crawling, translation, glossary work,
QA analysis, and ebook export remain out of scope.

The clean repository has no reusable package modules yet. The legacy
`../dich-truyen-tien-hiep` application is useful as a behavioral reference,
especially its Pydantic `StyleTemplate` and `yaml.safe_load()` style loading, but its direct
canonical YAML writes are not sufficient for the new interruption-safety requirement. Build
fresh contracts rather than porting the old application's combined progress model.

## Recommended Architecture

### Package Layout

```text
src/dich_truyen_agent/
  __init__.py
  cli.py
  models.py
  paths.py
  storage.py
  workspace.py
  checkpoints.py
  styles.py
tests/
  conftest.py
  test_storage.py
  test_workspace.py
  test_checkpoints.py
  test_styles.py
templates/styles/tien_hiep.yaml
.codex/skills/
  crawl-book/SKILL.md
  translate-book/SKILL.md
  check-translation/SKILL.md
  export-book/SKILL.md
```

Keep persisted models centralized initially. Split by domain only after the contracts become
large enough to justify additional modules. Use `src/` packaging and expose deterministic
helpers through a small CLI so skills can invoke helpers without importing application code.

### Workspace Contract

Use `books/<book-slug>/` as the root and create these stage-oriented paths:

```text
books/<book-slug>/
  book.yaml
  chapters.yaml
  state.yaml
  style.yaml
  raw/
  translations/
  staging/
  reports/
  checkpoints/
  exports/
```

`chapters.yaml` contains immutable catalog facts: stable numeric ID, readable slug, source URL,
original title, and canonical raw/translation filenames. `state.yaml` contains mutable stage
status and compact failure metadata. This separation is required so resume can validate
completed files without silently rewriting source facts.

Use stable chapter filenames such as `0001-chuong-mo-dau.txt`. Generate readable slugs with an
ASCII-safe fallback so Chinese-only titles still produce deterministic filenames.

### Validated YAML Boundaries

Use Pydantic v2 models for every persisted YAML file and `yaml.safe_load()` for parsing. Use
UTF-8 and `yaml.safe_dump(..., allow_unicode=True, sort_keys=False)` for human-readable output.

Recommended models:

| Model | Purpose |
|-------|---------|
| `BookMetadata` | Book slug, source URL, title, author, schema version |
| `ChapterCatalogEntry` / `ChapterCatalog` | Immutable chapter identity and canonical filenames |
| `ChapterState` / `BookState` | Mutable per-stage status, hashes, timestamps, compact errors |
| `CheckpointRecord` | Approval type, timestamp, report path, evidence hashes |
| `TranslationStyle` | Name, description, guidelines, vocabulary, tone, examples |
| `OperationResult` | Concise terminal and result-file status metadata |

Reject malformed YAML, unknown checkpoint types, duplicate chapter IDs, duplicate canonical
filenames, and state entries that do not correspond to catalog entries.

### Atomic Writes and Resume

All canonical YAML/result writes should follow one helper:

1. Serialize the validated model to a uniquely named temporary sibling file.
2. Flush and `os.fsync()` the temporary file.
3. Validate the serialized data by loading it through the destination model.
4. Replace the canonical path with `os.replace()`.
5. Leave orphan temporary files untouched if interrupted; report them during workspace
   inspection or resume.

The temporary sibling and canonical file stay on the same filesystem, which is required for
atomic replacement semantics. Do not delete orphan temporary files automatically because they
are useful diagnostics.

Resume must refuse to continue when `state.yaml` marks work complete but the corresponding
canonical file is missing, unreadable, invalid, or hash-mismatched. Valid completed work is
preserved. Initialization refuses an existing workspace unless the caller explicitly selects
resume.

### Approval Gates

Store each approval as `checkpoints/<checkpoint-type>.yaml`. The record includes:

- checkpoint type
- approved timestamp
- report path
- evidence hashes keyed by reviewed input path

Create checkpoint records only through an explicit approval command. A gate helper reloads the
record, recalculates hashes, and returns a compact result: allowed status, checkpoint type,
reason, report path, and approval path. A missing or stale record blocks the caller.

Phase 1 only needs a generic mechanism plus tests. Later phases decide which reports and inputs
feed `crawl-approved` and `qa-approved`.

### Styles

Use the legacy application's Pydantic `StyleTemplate` behavior as a reference, but narrow it to
the new file contract. Ship `templates/styles/tien_hiep.yaml`; initialization copies the
selected bundled or custom style into workspace-local `style.yaml`. Validate before copying and
write the snapshot atomically. Resume reads the workspace snapshot instead of silently picking
up changes from a shared template.

### Skill Skeletons

Create thin project-local `.codex/skills/<name>/SKILL.md` entrypoints for:

- `$crawl-book`
- `$translate-book`
- `$check-translation`
- `$export-book`

Each skeleton documents arguments, workspace paths, expected helper/result boundaries, required
checkpoint, and its current unfinished-step failure. Do not fake later-phase behavior. Skills
should print compact metadata and point to reports rather than inject logs or chapter bodies
into agent context.

## Validation Architecture

Use offline `pytest` tests with `tmp_path`; no network or browser setup is needed for Phase 1.
Configure `uv run pytest` as the full suite and narrow file-level test commands as the fast
feedback loop.

| Requirement | Automated Coverage |
|-------------|--------------------|
| WORK-01 | Initialize a new temp workspace and assert documented files/folders exist |
| WORK-02 | Round-trip catalog and state YAML; reject duplicate/mismatched entries |
| WORK-03 | Simulate interrupted temp write, confirm canonical survives, and verify resume preserves valid completion |
| WORK-04 | Verify missing and stale approvals block while current hashes allow |
| STYL-01 | Initialize using a custom valid YAML style and reject malformed style YAML |
| STYL-02 | Initialize without override and assert workspace `style.yaml` matches bundled `tien_hiep` contract |

Add a failure-injection test around atomic replacement by placing a valid canonical file and an
orphan temporary sibling, then loading/resuming the workspace. Also test a completed state entry
whose canonical file is missing or hash-mismatched.

## Security Notes

Phase 1 is local-only but still has trust boundaries:

| Threat | Mitigation |
|--------|------------|
| Path traversal through book slug or filename | Reject separators, `..`, absolute paths, and paths escaping the expected workspace root |
| Malicious YAML object construction | Use `yaml.safe_load()` only, then Pydantic validation |
| Stale approval after input mutation | Recompute evidence hashes at every gate check |
| Canonical corruption during write | Validate temp serialization and promote with `os.replace()` |
| Accidental overwrite of existing book | Refuse initialization unless explicit resume is selected |

Each execution plan should include a `<threat_model>` block and tests for path traversal,
unsafe/malformed YAML, stale approvals, and overwrite refusal.

## Planning Implications

Split Phase 1 into the two roadmap plans:

1. `01-01`: packaging, validated persisted contracts, deterministic paths, atomic YAML writes,
   workspace initialization, inspection, and strict resume validation.
2. `01-02`: checkpoint create/check helpers, style validation and snapshotting, bundled
   `tien_hiep.yaml`, compact CLI commands/results, and the four project-local skill skeletons.

`01-02` depends on `01-01` because gates and style snapshots consume workspace paths, validated
models, and atomic storage helpers.

## Package Legitimacy Audit

> Required because Phase 1 installs external Python packages. Verified on 2026-05-31 with
> `slopcheck install pydantic PyYAML pytest ruff` and `python -m pip index versions <package>`.
> The installed `slopcheck` version does not support the newer `--json` flag, so its supported
> plain-text verdicts were used.

| Package | Registry | Current PyPI Version | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|----------------------|-----------|-------------|-----------|-------------|
| `pydantic` | PyPI | `2.13.4` | Not reported by `pip index` | `github.com/pydantic/pydantic` | `[OK]` | Approved |
| `PyYAML` | PyPI | `6.0.3` | Not reported by `pip index` | `github.com/yaml/pyyaml` | `[OK]` | Approved |
| `pytest` | PyPI | `9.0.3` | Not reported by `pip index` | `github.com/pytest-dev/pytest` | `[OK]` | Approved |
| `ruff` | PyPI | `0.15.15` | Not reported by `pip index` | `github.com/astral-sh/ruff` | `[OK]` | Approved |

**Packages removed due to slopcheck `[SLOP]` verdict:** none
**Packages flagged as suspicious `[SUS]`:** none

## Sources

- `.planning/phases/01-workspace-contracts-and-skill-skeletons/01-CONTEXT.md`
- `.planning/REQUIREMENTS.md`
- `.planning/PROJECT.md`
- `.planning/research/STACK.md`
- `../dich-truyen-tien-hiep/src/dich_truyen/translator/style.py`
- `../dich-truyen-tien-hiep/styles/tien_hiep.yaml`
- `../dich-truyen-tien-hiep/src/dich_truyen/utils/progress.py`

---

*Phase: 01-workspace-contracts-and-skill-skeletons*
*Research complete: 2026-05-31*
