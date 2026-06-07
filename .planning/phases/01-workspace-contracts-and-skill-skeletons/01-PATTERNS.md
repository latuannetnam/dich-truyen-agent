# Phase 1: Workspace Contracts and Skill Skeletons - Pattern Map

**Mapped:** 2026-05-31
**Files analyzed:** 17 new files
**Current-code analogs found:** 0 / 17
**Legacy behavioral references found:** 2

## Scope Note

The current repository is intentionally minimal: `main.py` is a hello-world entrypoint and
`pyproject.toml` is an empty Python 3.13 `uv` scaffold. There are no package modules, tests, or
product skills to copy. Phase 1 establishes the first stable implementation conventions.

Legacy references from `../dich-truyen-tien-hiep` are behavioral references
only. Do not port its combined `BookProgress` schema or direct canonical writes wholesale.

## File Classification

| New File | Role | Data Flow | Closest Analog | Match Quality |
|----------|------|-----------|----------------|---------------|
| `src/dich_truyen_agent/__init__.py` | config/package | transform | None in current repo | no analog |
| `src/dich_truyen_agent/models.py` | model | transform | Legacy `src/dich_truyen/utils/progress.py` and `translator/style.py` | behavioral reference |
| `src/dich_truyen_agent/paths.py` | utility | file-I/O | None in current repo | no analog |
| `src/dich_truyen_agent/storage.py` | utility | file-I/O | Legacy direct writes are a non-example | no safe analog |
| `src/dich_truyen_agent/workspace.py` | service | file-I/O | Legacy `src/dich_truyen/utils/progress.py` | partial behavioral reference |
| `src/dich_truyen_agent/checkpoints.py` | service | file-I/O | None in current or legacy repo | no analog |
| `src/dich_truyen_agent/styles.py` | service | file-I/O | Legacy `src/dich_truyen/translator/style.py` | role-match behavioral reference |
| `src/dich_truyen_agent/cli.py` | controller | request-response | `main.py` only establishes a standard-library entrypoint | weak scaffold reference |
| `tests/conftest.py` | test config | file-I/O | None in current repo | no analog |
| `tests/test_storage.py` | test | file-I/O | None in current repo | no analog |
| `tests/test_workspace.py` | test | file-I/O | None in current repo | no analog |
| `tests/test_checkpoints.py` | test | file-I/O | None in current repo | no analog |
| `tests/test_styles.py` | test | file-I/O | None in current repo | no analog |
| `templates/styles/tien_hiep.yaml` | config | file-I/O | Legacy `styles/tien_hiep.yaml` | role-match behavioral reference |
| `.codex/skills/crawl-book/SKILL.md` | skill entrypoint | request-response | Existing GSD `SKILL.md` files only for frontmatter shape | partial structure reference |
| `.codex/skills/translate-book/SKILL.md` | skill entrypoint | request-response | Existing GSD `SKILL.md` files only for frontmatter shape | partial structure reference |
| `.codex/skills/check-translation/SKILL.md` | skill entrypoint | request-response | Existing GSD `SKILL.md` files only for frontmatter shape | partial structure reference |
| `.codex/skills/export-book/SKILL.md` | skill entrypoint | request-response | Existing GSD `SKILL.md` files only for frontmatter shape | partial structure reference |

## Pattern Assignments

### `src/dich_truyen_agent/models.py` (model, transform)

**Legacy behavioral references:**
- `../dich-truyen-tien-hiep/src/dich_truyen/translator/style.py:13`
- `../dich-truyen-tien-hiep/src/dich_truyen/utils/progress.py:12`

Copy the Pydantic-v2 modeling style, `Field` descriptions, enums for bounded statuses, and
`model_validate()` boundary validation:

```python
class StyleTemplate(BaseModel):
    name: str = Field(description="Style name")
    description: str = Field(description="Style description in Vietnamese")
    guidelines: list[str] = Field(default_factory=list, description="Translation guidelines")
    vocabulary: dict[str, str] = Field(default_factory=dict, description="Word/phrase mappings")
    tone: str = Field(default="formal", description="Tone: formal, casual, archaic")
```

```python
class ChapterStatus(str, Enum):
    PENDING = "pending"
    CRAWLED = "crawled"
    TRANSLATED = "translated"
    FORMATTED = "formatted"
    EXPORTED = "exported"
    ERROR = "error"
```

Create fresh centralized models for `BookMetadata`, `ChapterCatalogEntry`, `ChapterCatalog`,
`ChapterState`, `BookState`, `CheckpointRecord`, `TranslationStyle`, and `OperationResult`.
Unlike legacy `BookProgress`, keep immutable `chapters.yaml` facts separate from mutable
`state.yaml` progress. Add validators for duplicate chapter IDs, duplicate filenames, unknown
checkpoint types, and state entries missing from the catalog.

### `src/dich_truyen_agent/paths.py` (utility, file-I/O)

**Current analog:** None.

Introduce the first deterministic path convention. Centralize `books/<book-slug>/`, canonical
YAML paths, stage directories, checkpoint paths, result paths, and temporary sibling naming.
Reject absolute paths, separators, `..`, and any resolved path outside the expected workspace
root. Generate stable chapter filenames such as `0001-chuong-mo-dau.txt` with an ASCII-safe
fallback for Chinese-only titles.

### `src/dich_truyen_agent/storage.py` (utility, file-I/O)

**Legacy non-example:** `../dich-truyen-tien-hiep/src/dich_truyen/utils/progress.py:110`

Do not copy this direct canonical write:

```python
with open(progress_file, "w", encoding="utf-8") as f:
    json.dump(self.model_dump(mode="json"), f, ensure_ascii=False, indent=2, default=str)
```

Create the first safe persistence pattern: validate model, serialize UTF-8 YAML using
`yaml.safe_dump(..., allow_unicode=True, sort_keys=False)`, write a uniquely named sibling temp
file, flush, `os.fsync()`, reload through the destination Pydantic model, then `os.replace()`.
Loading must use `yaml.safe_load()`. Report orphan temp files without deleting or promoting
them.

### `src/dich_truyen_agent/workspace.py` (service, file-I/O)

**Legacy partial reference:** `../dich-truyen-tien-hiep/src/dich_truyen/utils/progress.py:117`

Legacy load behavior validates parsed persisted data:

```python
with open(progress_file, "r", encoding="utf-8") as f:
    data = json.load(f)
return cls.model_validate(data)
```

Retain boundary validation but build fresh YAML workspace initialization and resume inspection.
Initialization creates `book.yaml`, `chapters.yaml`, `state.yaml`, `style.yaml`, `raw/`,
`translations/`, `staging/`, `reports/`, `checkpoints/`, and `exports/`. Refuse an existing
workspace unless resume is explicit. Resume preserves valid completed files and stops on
missing, unreadable, invalid, or hash-mismatched canonical files.

### `src/dich_truyen_agent/checkpoints.py` (service, file-I/O)

**Current analog:** None.

Add a generic explicit approval helper and gate checker. Write
`checkpoints/<checkpoint-type>.yaml` through `storage.py`; include checkpoint type, approval
timestamp, report path, and evidence hashes keyed by reviewed input path. Gate checking reloads
the record, recomputes hashes, and returns compact allowed/blocked metadata with reason, report
path, and approval path.

### `src/dich_truyen_agent/styles.py` (service, file-I/O)

**Legacy behavioral reference:** `../dich-truyen-tien-hiep/src/dich_truyen/translator/style.py:72`

Copy the safe-load plus Pydantic-validation boundary:

```python
with open(path, "r", encoding="utf-8") as f:
    data = yaml.safe_load(f)
return cls.model_validate(data)
```

Narrow the legacy manager behavior to Phase 1: load bundled or custom YAML, validate it, then
atomically snapshot it as workspace-local `style.yaml`. Resume reads the snapshot. Do not add
legacy LLM style generation, registry caching, mutation, or deletion.

### `src/dich_truyen_agent/cli.py` (controller, request-response)

**Weak local scaffold reference:** `main.py:1`

```python
def main():
    print("Hello from dich-truyen-agent!")
```

Keep a small standard-library CLI entrypoint. Expose deterministic helper commands for
initialization/resume inspection, checkpoint approval/checking, and style validation or
snapshotting. Print concise `OperationResult` summaries: status, reason, progress, and report
paths. Do not print chapter bodies or verbose logs.

### Tests (test, file-I/O)

**Current analog:** None.

Use offline `pytest` with `tmp_path`. Organize tests by owning module:

| Test File | Required Coverage |
|-----------|-------------------|
| `tests/conftest.py` | reusable temp workspace inputs only when duplication appears |
| `tests/test_storage.py` | YAML round-trip, malformed/unsafe YAML, interrupted write, orphan temp reporting |
| `tests/test_workspace.py` | documented layout, overwrite refusal, traversal rejection, valid resume preservation, missing/hash-mismatched completed file rejection |
| `tests/test_checkpoints.py` | missing approval blocks, current evidence allows, mutated evidence invalidates |
| `tests/test_styles.py` | valid custom snapshot, malformed style rejection, bundled `tien_hiep` default |

### `templates/styles/tien_hiep.yaml` (config, file-I/O)

**Legacy behavioral reference:** `../dich-truyen-tien-hiep/styles/tien_hiep.yaml`

Use the legacy YAML shape: `name`, `description`, `guidelines`, `vocabulary`, `tone`, and
`examples`. Ship one reviewed bundled template. Workspace initialization copies a validated
snapshot; it must not retain a live reference to this shared template.

### `.codex/skills/*/SKILL.md` (skill entrypoint, request-response)

**Partial structural reference:** `.codex/skills/gsd-plan-phase/SKILL.md:1`

```yaml
---
name: "gsd-plan-phase"
description: "Create detailed phase plan (PLAN.md) with verification loop"
metadata:
  short-description: "Create detailed phase plan (PLAN.md) with verification loop"
---
```

Create `crawl-book`, `translate-book`, `check-translation`, and `export-book` skeletons with
frontmatter plus documented arguments, workspace paths, helper/result boundaries, required
checkpoint, and explicit unfinished-step failure. Do not fake later-phase behavior.

## Shared Patterns

### Persisted Boundary Validation

Apply to `models.py`, `storage.py`, `workspace.py`, `checkpoints.py`, and `styles.py`.

```python
with open(path, "r", encoding="utf-8") as f:
    data = yaml.safe_load(f)
return Model.model_validate(data)
```

Every persisted YAML boundary uses `yaml.safe_load()` followed by Pydantic-v2 validation.

### Atomic Canonical Writes

Apply to every YAML or result-file writer. There is no safe current or legacy analog.

```python
# Required shape, not copied implementation:
# sibling temp -> flush -> os.fsync -> reload/validate -> os.replace
```

Never write canonical persisted files directly. Never auto-delete or promote orphan temps.

### Compact Results

Apply to `cli.py`, checkpoint gates, workspace inspection, and all future helper-facing skill
contracts. Return status, reason, progress, and report paths; keep chapter contents and verbose
logs out of agent context.

### Skill Boundaries

Apply to all four Phase-1 skeletons. Skills are thin Codex-facing orchestration documents;
deterministic filesystem behavior remains in Python helpers.

## No Current Analog Found

All new product files lack a copyable current-code analog because Phase 1 creates the initial
package. Use the assignments above as first conventions. The planner should treat legacy
references as behavioral guidance and implement fresh contracts where Phase 1 safety rules are
stronger.

## Metadata

**Current code searched:** `main.py`, `pyproject.toml`, `README.md`, `AGENTS.md`, `.codex/skills/`
**Legacy files inspected:** `translator/style.py`, `utils/progress.py`, `styles/tien_hiep.yaml`
**Current product files scanned:** 4 scaffold files
**Pattern extraction date:** 2026-05-31
