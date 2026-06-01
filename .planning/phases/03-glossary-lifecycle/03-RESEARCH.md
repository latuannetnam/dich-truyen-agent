# Phase 3: Glossary Lifecycle - Research

**Researched:** 2026-06-01
**Domain:** Glossary structured schema, automatic LLM-based glossary generation, progressive merging, non-blocking conflict resolution, and automatic snapshot backups.
**Confidence:** HIGH

## Summary

Phase 3 establishes a robust glossary lifecycle to maintain terminology consistency across sequential chapters. This phase defines the rich structured metadata schema for `glossary.yaml`, implements an automated initial glossary generation strategy using an LLM scan over the first few raw chapters, introduces a progressive non-blocking merge workflow for subagent term proposals that prioritizes manual locks (`is_canonical: true`) and writes conflicts to a dedicated report file, and enables automatic backup snapshots before merging proposals.

## Recommended Architecture

### Models and Data Schema (`src/dich_truyen_agent/models.py`)

To implement **Structured Term Schema (D-01)**, we will add the following Pydantic models to `models.py`:

```python
class GlossaryTerm(PersistedModel):
    translation: str = Field(min_length=1)
    category: str = Field(default="other")  # character, sect, location, item, cultivation, other
    source: str = Field(min_length=1)      # manual, initial_generation, chapter_N_proposal
    is_canonical: bool = Field(default=False)
    note: str | None = None

class BookGlossary(PersistedModel):
    schema_version: int = 1
    terms: dict[str, GlossaryTerm] = Field(default_factory=dict)  # Chinese term -> GlossaryTerm
```

To support **Conflict Handling (D-03)**, we will model conflicts deterministically:

```python
class GlossaryConflict(PersistedModel):
    term: str
    existing_translation: str
    existing_source: str
    proposed_translation: str
    proposed_source: str
    chapter_id: int

class GlossaryConflictReport(PersistedModel):
    schema_version: int = 1
    conflicts: list[GlossaryConflict] = Field(default_factory=list)
```

### Workspace Paths Extension (`src/dich_truyen_agent/paths.py`)

We will update `WorkspacePaths` and `workspace_paths()` to include the glossary and snapshot paths:

* `glossary`: `books/<book-slug>/glossary.yaml`
* `glossary_snapshots`: `books/<book-slug>/checkpoints/glossary-snapshots`
* `glossary_conflicts`: `books/<book-slug>/reports/glossary-conflicts.yaml`

We will add `self.glossary_snapshots` to `stage_directories` so that the folder is created automatically during workspace initialization or repair.

### Core Helpers (`src/dich_truyen_agent/glossary.py`)

We will create a new module `src/dich_truyen_agent/glossary.py` containing the core logic:

#### 1. Initial Glossary Generation (`GLOS-01`, `D-02`)
* Function: `generate_initial_glossary(workspace_root: Path, sample_chapter_ids: list[int] = [1, 2, 3]) -> OperationResult`
* Behavior: Reads the raw contents of the designated sample chapters. Executes an LLM scan pass (via an agent-native worker or direct LLM integration helper) to extract unique Chinese terms (characters, sects, locations, items, cultivation ranks) with their Vietnamese translations, categories, and optional context. Writes the result to `glossary.yaml` with `is_canonical: false` and `source: initial_generation`.

#### 2. Progressive Merging & Snapshotting (`GLOS-02`, `GLOS-03`, `D-03`, `D-04`)
* Function: `merge_glossary_proposals(workspace_root: Path, chapter_id: int, proposals: dict[str, GlossaryTerm]) -> OperationResult`
* Behavior:
  1. Load existing `glossary.yaml`. If it doesn't exist, initialize an empty `BookGlossary`.
  2. Create a backup snapshot of `glossary.yaml` as `checkpoints/glossary-snapshots/chapter-{chapter_id:04d}.yaml`.
  3. Load the existing conflict report at `reports/glossary-conflicts.yaml` (if it exists).
  4. Iterate through `proposals`:
     * If the Chinese term is **brand new**: Add to `terms` with `is_canonical: false`.
     * If the term **already exists**:
       * If the translations match: Skip (no action needed).
       * If the translations differ:
         * Preserve the existing term (especially if `is_canonical: true`).
         * Create a `GlossaryConflict` entry (capturing the term, existing value/source, proposed value, and the proposing chapter) and append it to `reports/glossary-conflicts.yaml`.
         * Print a console warning containing the mismatch details.
  5. Write the updated `BookGlossary` and `GlossaryConflictReport` atomically.
  6. Return an `OperationResult` summarizing the number of merged terms and recorded conflicts.

### CLI Extensions (`src/dich_truyen_agent/cli.py`)

We will add commands to support glossary operations:

* `dich-truyen-agent generate-glossary <book-slug> [--chapters <csv_ids>]`: Triggers the initial scan.
* `dich-truyen-agent merge-proposals <book-slug> <chapter-id> <proposals-yaml-path>`: Merges chapter proposals.
* `dich-truyen-agent lock-term <book-slug> <chinese-term>`: Helper to manually lock a term (set `is_canonical: true`).

## Validation Architecture

We will implement isolated unit and integration tests under `tests/test_glossary.py` to verify:

| Requirement | Automated Coverage |
|-------------|--------------------|
| **GLOS-01** | Test initial glossary generation scans raw chapters, produces valid `BookGlossary`, and populates correct schema metadata. |
| **GLOS-02** | Test merging proposals with correct `source: chapter_N_proposal` attributes. |
| **GLOS-03** | Verify non-blocking merge: brand new terms are added, identical terms are skipped, mismatching translations are preserved while logging conflicts in `reports/glossary-conflicts.yaml` and outputting warnings. |
| **GLOS-04** | Verify automatic snapshot backups are created under `checkpoints/glossary-snapshots/` prior to any merge operations, and that manually locked terms (`is_canonical: true`) cannot be overwritten by proposals. |

## Security Notes

| Threat | Mitigation |
|--------|------------|
| Path traversal in snapshot naming | Enforce strict integer formatting on `chapter_id` to prevent directory traversal via `chapter_id = "../../foo"`. |
| Unsafe YAML loading | Use `yaml.safe_load()` in `storage.py` (which is already established). |
| Partial/corrupt glossary writes | Write to a temporary sibling file and promote atomically using `os.replace()`, utilizing `atomic_write_yaml()`. |

## Planning Implications

We will split Phase 3 into the two roadmap plans:

1. `03-01`: Define paths, Pydantic glossary and conflict models, CLI skeletons, and the LLM/agent scan helper for generating the initial glossary from sample chapters.
2. `03-02`: Implement progressive merge logic, conflict reporting, backup snapshots, `is_canonical` manual override enforcement, and full integration tests.

---

*Phase: 03-glossary-lifecycle*
*Research complete: 2026-06-01*
