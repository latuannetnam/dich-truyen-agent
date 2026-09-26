# Unified Orchestrator CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable running a novel translation workflow from a source URL to finished EPUB/PDF via a single `orchestrate` CLI command with auto-initialization, scoped prefix limits, interactive terminal approval prompts, and unattended `--yes` execution while preserving immutable checkpoints, external locks, and sequential invariants.

**Architecture:** Extend deterministic domain operations with a versioned `reports/source-scope.yaml` bound to gate hashes; migrate orchestrator locking to `<books-root>/.orchestrator-locks/<slug>.lock`; integrate auto-initialization and clean-only `--yes` in `cli.py`; and wrap paused graph interrupts in a TTY `[y/N]` prompt that calls `orchestrator.resume_run(...)` without starting new processes.

**Tech Stack:** Python 3.13, LangGraph StateGraph, SQLite checkpointer, Pydantic/dataclasses, Pytest, Calibre `ebook-convert`, `epubcheck.jar`, Antigravity CLI (`agy`).

---

### Task 1: Source Scope Model and Scope Evidence Persistence

**Files:**
- Create: `src/dich_truyen_agent/scope.py`
- Modify: `src/dich_truyen_agent/models.py`
- Modify: `src/dich_truyen_agent/paths.py`
- Test: `tests/test_source_scope.py`

- [ ] **Step 1: Write the failing test for source scope model and persistence**

```python
from pathlib import Path
import pytest
from dich_truyen_agent.models import SourceCatalogEntry, SourceScopeRecord
from dich_truyen_agent.paths import workspace_paths
from dich_truyen_agent.scope import save_source_scope, load_source_scope, compute_source_digest

def test_source_scope_roundtrip(tmp_path: Path) -> None:
    paths = workspace_paths(tmp_path, "test-book")
    paths.reports.mkdir(parents=True, exist_ok=True)

    entries = [
        SourceCatalogEntry(position=1, chapter_id=1, url="https://example.com/1", title="Chương 1", ordinal=1),
        SourceCatalogEntry(position=2, chapter_id=2, url="https://example.com/2", title="Chương 2", ordinal=2),
        SourceCatalogEntry(position=3, chapter_id=3, url="https://example.com/3", title="Chương 3", ordinal=3),
    ]
    digest = compute_source_digest(entries)
    record = SourceScopeRecord(
        schema_version=1,
        source_url="https://example.com",
        source_discovered_count=3,
        source_digest=digest,
        selection_mode="prefix",
        requested_limit=2,
        selected_count=2,
        selected_chapter_ids=[1, 2],
        full_source_entries=entries,
    )
    saved_path = save_source_scope(paths.root, record)
    assert saved_path.is_file()
    assert saved_path == paths.reports / "source-scope.yaml"

    loaded = load_source_scope(paths.root)
    assert loaded is not None
    assert loaded.source_discovered_count == 3
    assert loaded.selected_count == 2
    assert loaded.selected_chapter_ids == [1, 2]
    assert loaded.source_digest == digest
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/test_source_scope.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'dich_truyen_agent.scope'`

- [ ] **Step 3: Implement SourceScopeRecord in models.py, paths.py, and scope.py**

In `src/dich_truyen_agent/models.py`, define:
```python
class SourceCatalogEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    position: int
    chapter_id: int
    url: str
    title: str
    ordinal: int | None = None

class SourceScopeRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: int = 1
    discovered_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    source_url: str
    source_discovered_count: int
    source_digest: str
    selection_mode: Literal["full", "prefix"]
    requested_limit: int | None = None
    selected_count: int
    selected_chapter_ids: list[int]
    full_source_entries: list[SourceCatalogEntry]
```

In `src/dich_truyen_agent/paths.py`, add `source_scope` property:
```python
@property
def source_scope(self) -> Path:
    return self.reports / "source-scope.yaml"
```

In `src/dich_truyen_agent/scope.py`, implement `compute_source_digest`, `save_source_scope`, and `load_source_scope` using atomic YAML storage.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/test_source_scope.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dich_truyen_agent/models.py src/dich_truyen_agent/paths.py src/dich_truyen_agent/scope.py tests/test_source_scope.py
git commit -m "feat(scope): add source scope record model, path, and persistence helpers"
```

---

### Task 2: Scoped Discovery and Crawl Report Extensions

**Files:**
- Modify: `src/dich_truyen_agent/crawler.py`
- Modify: `src/dich_truyen_agent/crawl_reports.py`
- Modify: `src/dich_truyen_agent/models.py`
- Test: `tests/test_scoped_crawler.py`

- [ ] **Step 1: Write the failing test for scoped crawling and report counters**

```python
from pathlib import Path
import pytest
from dich_truyen_agent.crawler import crawl_book_scoped
from dich_truyen_agent.models import BookMetadata, ChapterCatalog, ChapterCatalogEntry, TranslationStyle
from dich_truyen_agent.paths import workspace_paths
from dich_truyen_agent.storage import load_yaml_model
from dich_truyen_agent.workspace import initialize_workspace
from dich_truyen_agent.scope import load_source_scope

def test_crawl_book_scoped_prefix_limit(tmp_path: Path, monkeypatch) -> None:
    books_root = tmp_path / "books"
    slug = "prefix-book"
    metadata = BookMetadata(book_slug=slug, source_url="https://example.com/novel", title="Test Novel")
    style = TranslationStyle(name="general", rules=["rule1"])
    initialize_workspace(books_root, metadata, ChapterCatalog(), style)
    workspace = workspace_paths(books_root, slug).root

    # Mock discovery returning 5 chapters
    discovered = [
        ChapterCatalogEntry(chapter_id=i, slug=str(i), source_url=f"https://example.com/c{i}", original_title=f"Ch {i}", raw_filename=f"{i:04d}-{i}.txt", translation_filename=f"{i:04d}-{i}.txt")
        for i in range(1, 6)
    ]
    monkeypatch.setattr("dich_truyen_agent.crawler.discover_source_catalog", lambda url: ("Test Novel", discovered))
    monkeypatch.setattr("dich_truyen_agent.crawler.fetch_raw_chapter", lambda url, dest: dest.write_text(f"Content for {url}", encoding="utf-8"))

    res = crawl_book_scoped(workspace, limit=2)
    assert res.status.value == "ok"

    # Catalog and state must contain exactly 2 selected chapters
    catalog = load_yaml_model(workspace / "chapters.yaml", ChapterCatalog)
    assert len(catalog.chapters) == 2
    assert [c.chapter_id for c in catalog.chapters] == [1, 2]

    # Scope record must persist source 5 vs selected 2
    scope = load_source_scope(workspace)
    assert scope is not None
    assert scope.source_discovered_count == 5
    assert scope.selected_count == 2
    assert scope.selection_mode == "prefix"

    # Crawl report must record source and selected counts
    from dich_truyen_agent.models import CrawlReport
    report = load_yaml_model(workspace / "reports" / "crawl.yaml", CrawlReport)
    assert report.summary.get("source_discovered_count") == 5
    assert report.summary.get("selected_count") == 2
    assert report.summary.get("scope_summary") == "prefix 2 of 5"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/test_scoped_crawler.py`
Expected: FAIL with `ImportError: cannot import name 'crawl_book_scoped'`

- [ ] **Step 3: Implement `crawl_book_scoped` and report summaries**

In `src/dich_truyen_agent/crawler.py`:
- Implement `crawl_book_scoped(workspace_root: Path, limit: int | None = None) -> OperationResult`.
- Discover full catalog, validate ordering and absence of gaps.
- If `limit` is given: validate `limit > 0` and `limit <= len(discovered)`. Select first `limit` chapters.
- Persist `source-scope.yaml` via `save_source_scope`.
- Download raw texts only for selected chapters.
- In `src/dich_truyen_agent/crawl_reports.py`: add `source_discovered_count`, `selected_count`, and `scope_summary` to `CrawlReportSummary`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/test_scoped_crawler.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dich_truyen_agent/crawler.py src/dich_truyen_agent/crawl_reports.py src/dich_truyen_agent/models.py tests/test_scoped_crawler.py
git commit -m "feat(crawler): implement scoped crawling with source scope record and prefix report summary"
```

---

### Task 3: Scope Evidence in Crawl & QA Approvals and Gate Checks

**Files:**
- Modify: `src/dich_truyen_agent/checkpoints.py`
- Modify: `src/dich_truyen_agent/orchestrator/graph.py`
- Test: `tests/test_scope_gate_evidence.py`

- [ ] **Step 1: Write the failing test for scope record binding in approval evidence**

```python
from pathlib import Path
import pytest
from dich_truyen_agent.checkpoints import approve_checkpoint, check_gate
from dich_truyen_agent.models import CheckpointType, OperationStatus
from dich_truyen_agent.paths import workspace_paths
from dich_truyen_agent.storage import sha256_file
from dich_truyen_agent.scope import save_source_scope, SourceScopeRecord, SourceCatalogEntry

def test_scope_record_hashed_in_crawl_approval(tmp_path: Path) -> None:
    paths = workspace_paths(tmp_path, "scope-gate-book")
    paths.reports.mkdir(parents=True, exist_ok=True)
    paths.raw.mkdir(parents=True, exist_ok=True)

    # Create dummy chapters, raw, and scope record
    paths.chapters.write_text("schema_version: 1\nchapters: []\n", encoding="utf-8")
    paths.crawl_report.write_text("schema_version: 1\nsummary: {}\n", encoding="utf-8")
    record = SourceScopeRecord(
        schema_version=1,
        source_url="https://example.com",
        source_discovered_count=1,
        source_digest="abc",
        selection_mode="prefix",
        selected_count=1,
        selected_chapter_ids=[1],
        full_source_entries=[SourceCatalogEntry(position=1, chapter_id=1, url="https://example.com/1", title="Ch 1")],
    )
    save_source_scope(paths.root, record)

    # Approve crawl checkpoint
    app_res = approve_checkpoint(paths.root, CheckpointType.CRAWL_APPROVED, "reports/crawl.yaml")
    assert app_res.status == OperationStatus.OK

    # Gate check must pass
    gate_res = check_gate(paths.root, CheckpointType.CRAWL_APPROVED)
    assert gate_res.status == OperationStatus.OK

    # Mutating source-scope.yaml must invalidate the gate check
    paths.source_scope.write_text("corrupted content", encoding="utf-8")
    tampered_gate = check_gate(paths.root, CheckpointType.CRAWL_APPROVED)
    assert tampered_gate.status == OperationStatus.BLOCKED
    assert "scope" in tampered_gate.reason.lower() or "evidence" in tampered_gate.reason.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/test_scope_gate_evidence.py`
Expected: FAIL because `paths.source_scope` is not yet hashed into evidence in `approve_checkpoint` / `check_gate`.

- [ ] **Step 3: Update `checkpoints.py` and `graph.py` evidence calculation**

In `src/dich_truyen_agent/checkpoints.py`:
- In `_compute_crawl_evidence_hashes`: if `paths.source_scope.is_file()`, include `"reports/source-scope.yaml": sha256_file(paths.source_scope)`.
- In `_compute_qa_evidence_hashes`: if `paths.source_scope.is_file()`, include `"reports/source-scope.yaml": sha256_file(paths.source_scope)`.
- For legacy workspaces where `source-scope.yaml` does not exist: do not require it (preserving backwards compatibility).
- In `src/dich_truyen_agent/orchestrator/graph.py`: ensure `_compute_crawl_evidence_hashes` and `_compute_qa_evidence_hashes` mirror these entries.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/test_scope_gate_evidence.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dich_truyen_agent/checkpoints.py src/dich_truyen_agent/orchestrator/graph.py tests/test_scope_gate_evidence.py
git commit -m "feat(checkpoints): bind source scope record into crawl and QA approval evidence hashes"
```

---

### Task 4: External Stable Lock Path Migration

**Files:**
- Modify: `src/dich_truyen_agent/paths.py`
- Modify: `src/dich_truyen_agent/orchestrator/orchestrator.py`
- Test: `tests/test_orchestrator_external_lock.py`

- [ ] **Step 1: Write the failing test for external stable workspace locking**

```python
from pathlib import Path
import pytest
from dich_truyen_agent.orchestrator.orchestrator import BookOrchestrator
from dich_truyen_agent.orchestrator.workspace_ops import WorkspaceOps
from dich_truyen_agent.orchestrator.runners.mock import MockRunner
from dich_truyen_agent.orchestrator.process import WorkspaceLock

def test_external_lock_path_and_no_unlink(tmp_path: Path) -> None:
    books_root = tmp_path / "books"
    slug = "locked-book"
    workspace_root = books_root / slug

    orch = BookOrchestrator(runner=MockRunner(), ops=WorkspaceOps())
    lock_file = orch._lock_path(workspace_root)

    # Lock must be outside workspace under .orchestrator-locks
    assert lock_file.parent == books_root / ".orchestrator-locks"
    assert lock_file.name == f"{slug}.lock"

    # Acquire and release lock
    lock = WorkspaceLock(lock_file)
    assert lock.acquire() is True
    lock.release()

    # Invariant: do not unlink lock file on release to prevent race conditions
    assert lock_file.is_file()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/test_orchestrator_external_lock.py`
Expected: FAIL because `orch._lock_path` still points inside workspace `.lock.json`.

- [ ] **Step 3: Implement external lock path in `paths.py` and `orchestrator.py`**

In `src/dich_truyen_agent/paths.py`:
Add helper:
```python
def orchestrator_lock_path(books_root: Path, slug: str) -> Path:
    locks_dir = books_root / ".orchestrator-locks"
    locks_dir.mkdir(parents=True, exist_ok=True)
    return locks_dir / f"{slug}.lock"
```
In `src/dich_truyen_agent/orchestrator/orchestrator.py`:
- Update `_lock_path(self, workspace_root: Path) -> Path`:
  Use `orchestrator_lock_path(workspace_root.parent, workspace_root.name)`.
- Ensure `WorkspaceLock.release()` does not delete the file.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/test_orchestrator_external_lock.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dich_truyen_agent/paths.py src/dich_truyen_agent/orchestrator/orchestrator.py tests/test_orchestrator_external_lock.py
git commit -m "fix(orchestrator): migrate lock path to external books/.orchestrator-locks/<slug>.lock without unlinking"
```

---

### Task 5: Auto-Initialization and Scope Binding in Orchestrator

**Files:**
- Modify: `src/dich_truyen_agent/orchestrator/models.py`
- Modify: `src/dich_truyen_agent/orchestrator/orchestrator.py`
- Modify: `src/dich_truyen_agent/orchestrator/graph.py`
- Test: `tests/test_orchestrator_auto_init.py`

- [ ] **Step 1: Write the failing test for auto-initialization via orchestrator**

```python
from pathlib import Path
import pytest
from dich_truyen_agent.orchestrator.models import OrchestratorConfig
from dich_truyen_agent.orchestrator.orchestrator import BookOrchestrator
from dich_truyen_agent.orchestrator.runners.mock import MockRunner
from dich_truyen_agent.orchestrator.workspace_ops import WorkspaceOps
from dich_truyen_agent.storage import load_yaml_model
from dich_truyen_agent.models import BookMetadata

def test_orchestrator_auto_init_when_workspace_absent(tmp_path: Path, monkeypatch) -> None:
    books_root = tmp_path / "books"
    slug = "auto-init-book"
    workspace_root = books_root / slug

    # Mock discovery of title and catalog
    from dich_truyen_agent.models import ChapterCatalogEntry
    monkeypatch.setattr("dich_truyen_agent.crawler.discover_source_catalog", lambda url: ("Auto Novel", [
        ChapterCatalogEntry(chapter_id=1, slug="1", source_url="https://example.com/1", original_title="Ch 1", raw_filename="0001-1.txt", translation_filename="0001-1.txt")
    ]))

    config = OrchestratorConfig(
        run_id="test-run-auto-init",
        workspace_root=workspace_root,
        source_url="https://example.com/novel",
        book_slug=slug,
        style_name="tien_hiep",
        scope_limit=1,
        stop_after="crawl",
    )
    orch = BookOrchestrator(runner=MockRunner(), ops=WorkspaceOps())
    outcome = orch.run(config)
    assert outcome.status in ("completed", "paused")
    assert workspace_root.is_dir()
    meta = load_yaml_model(workspace_root / "book.yaml", BookMetadata)
    assert meta.title == "Auto Novel"
    assert meta.source_url == "https://example.com/novel"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/test_orchestrator_auto_init.py`
Expected: FAIL with `TypeError: unexpected keyword argument 'source_url'` in `OrchestratorConfig`.

- [ ] **Step 3: Implement auto-initialization in `OrchestratorConfig` and `orchestrator.run`**

In `src/dich_truyen_agent/orchestrator/models.py`:
Add fields to `OrchestratorConfig`:
- `source_url: str | None = None`
- `book_slug: str | None = None`
- `book_title: str | None = None`
- `book_author: str | None = None`
- `style_name: str | None = None`
- `scope_limit: int | None = None`

In `src/dich_truyen_agent/orchestrator/orchestrator.py`:
- In `run(config)`:
  - Acquire external lock on `config.workspace_root`.
  - If `config.workspace_root` does not exist:
    - Validate `config.source_url` and `config.style_name` are present.
    - If `config.book_title` is omitted, discover title from `discover_source_catalog`.
    - Call `initialize_workspace` using domain operations.
    - If `config.scope_limit` is set, pass to scoped crawler.
  - Pin `scope_limit` in `run_summary.json`.
- In `src/dich_truyen_agent/orchestrator/graph.py`:
  - Pass `scope_limit` from `config` to scoped crawl operations.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/test_orchestrator_auto_init.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dich_truyen_agent/orchestrator/models.py src/dich_truyen_agent/orchestrator/orchestrator.py src/dich_truyen_agent/orchestrator/graph.py tests/test_orchestrator_auto_init.py
git commit -m "feat(orchestrator): add auto-init path and scope_limit configuration in graph runner"
```

---

### Task 6: Unified CLI Arguments and Validation

**Files:**
- Modify: `src/dich_truyen_agent/cli.py`
- Test: `tests/test_cli_unified_args.py`

- [ ] **Step 1: Write the failing test for unified CLI argument parsing and validation**

```python
import pytest
from pathlib import Path
from dich_truyen_agent.cli import build_parser

def test_unified_orchestrate_cli_arguments() -> None:
    parser = build_parser()

    # 1. New book unified invocation
    args = parser.parse_args([
        "orchestrate",
        "--url", "https://example.com/novel",
        "--slug", "novel-slug",
        "--style", "tien_hiep",
        "--limit", "3",
        "-y",
        "--formats", "epub,pdf",
    ])
    assert args.url == "https://example.com/novel"
    assert args.slug == "novel-slug"
    assert args.style == "tien_hiep"
    assert args.limit == 3
    assert args.yes is True
    assert args.formats == "epub,pdf"

    # 2. Existing workspace invocation remains backwards compatible
    args_ws = parser.parse_args([
        "orchestrate",
        "--workspace", "books/existing-book",
        "--start-at", "qa",
        "--resume",
    ])
    assert str(args_ws.workspace) == "books/existing-book"
    assert args_ws.start_at == "qa"
    assert args_ws.resume is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/test_cli_unified_args.py`
Expected: FAIL with `unrecognized arguments: --url --slug --limit -y`.

- [ ] **Step 3: Update `cli.py` arguments for `orchestrate`**

In `src/dich_truyen_agent/cli.py`:
- Make `--workspace` optional (`required=False`).
- Add `--url`, `--slug`, `--title`, `--author`, `--style`, `--limit` (type=int).
- Add `-y`, `--yes` (alias for `--auto-approve`).
- Validate input combinations in `run_command`:
  - If `--workspace` is absent: require both `--url` and `--slug`. Derive `workspace = PROJECT_ROOT / "books" / args.slug`.
  - If `--resume` is passed: reject `--url`, `--style`, `--limit` as creation-only inputs.
  - If `--limit` is passed: require `limit > 0`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/test_cli_unified_args.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dich_truyen_agent/cli.py tests/test_cli_unified_args.py
git commit -m "feat(cli): add unified CLI arguments --url, --slug, --style, --limit, -y for orchestrate"
```

---

### Task 7: CLI Interactive Approval Loop and `--yes` Handling

**Files:**
- Modify: `src/dich_truyen_agent/cli.py`
- Test: `tests/test_cli_interactive_approval.py`

- [ ] **Step 1: Write the failing test for interactive approval loop and `--yes` auto-approval**

```python
import sys
from pathlib import Path
import pytest
from dich_truyen_agent.cli import run_command, build_parser
from dich_truyen_agent.models import OperationStatus

def test_cli_interactive_approval_yes_flag(tmp_path: Path, monkeypatch) -> None:
    # Test that --yes auto-approves clean gates and returns completed
    parser = build_parser()
    args = parser.parse_args([
        "orchestrate",
        "--workspace", str(tmp_path / "mock-ws"),
        "-y",
    ])

    # Mock orchestrator run returning paused gate with 0 errors
    from dich_truyen_agent.orchestrator.models import RunOutcome
    call_count = 0
    def mock_run(self, config):
        nonlocal call_count
        call_count += 1
        return RunOutcome(status="paused", run_id="run-1", pending_approval="qa_approval", current_phase="qa_decision")

    def mock_resume(self, workspace_root, decision=None):
        return RunOutcome(status="completed", run_id="run-1", current_phase="export")

    monkeypatch.setattr("dich_truyen_agent.orchestrator.orchestrator.BookOrchestrator.run", mock_run)
    monkeypatch.setattr("dich_truyen_agent.orchestrator.orchestrator.BookOrchestrator.resume_run", mock_resume)

    res = run_command(args)
    assert res.status == OperationStatus.OK
    assert call_count == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest -q tests/test_cli_interactive_approval.py`
Expected: FAIL because `run_command` does not loop on paused outcomes.

- [ ] **Step 3: Implement interactive approval loop and report summary box in `cli.py`**

In `src/dich_truyen_agent/cli.py`:
- Wrap orchestrator invocation in `_run_orchestrate_with_interactive_loop`:
```python
outcome = orch.run(config)
while outcome.status == "paused":
    # If headless or --json: do not prompt, return paused outcome (exit 2)
    if args.json or not sys.stdin.isatty():
        break

    # Unattended clean-only mode
    if args.yes or args.auto_approve:
        # Load report and check error count
        rep = _load_pending_report(workspace_root, outcome.pending_approval)
        if rep and rep.get("error_count", 0) == 0 and rep.get("warning_count", 0) == 0:
            outcome = orch.resume_run(workspace_root, decision="approve")
            continue
        break

    # Interactive TTY prompt
    _print_interactive_gate_summary(workspace_root, outcome)
    prompt = "[?] Approve report and continue to next phase? [y/N]: "
    try:
        user_choice = input(prompt).strip().lower()
    except (EOFError, KeyboardInterrupt):
        break

    if user_choice in ("y", "yes"):
        outcome = orch.resume_run(workspace_root, decision="approve")
    elif user_choice in ("n", "no"):
        outcome = orch.resume_run(workspace_root, decision="reject")
        break
    else:
        # Empty or invalid input defers decision
        break
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -q tests/test_cli_interactive_approval.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dich_truyen_agent/cli.py tests/test_cli_interactive_approval.py
git commit -m "feat(cli): implement interactive terminal approval prompt and unattended clean-only --yes loop"
```

---

### Task 8: Documentation, Guides, and Adapter Synchronization

**Files:**
- Modify: `.harness/source/guides/shared-main-agent.md`
- Modify: `README.md`
- Modify: `ARCHITECTURE.md`
- Run: `tools/sync_harness_adapters.py`
- Test: `tools/sync_harness_adapters.py --check`

- [ ] **Step 1: Update source guide and repository documentation**

In `.harness/source/guides/shared-main-agent.md`:
- Document the unified single command:
  ```powershell
  $env:PYTHONUTF8=1
  uv run python main.py orchestrate --url "<source-url>" --slug <book-slug> --style <style> --limit <N> --formats epub,pdf --yes
  ```
- Explain the distinction between prefix-workspace completeness and full-source completeness.
- Document the clean-only `--yes` policy and interactive `[y/N]` prompt.
In `README.md` and `ARCHITECTURE.md`:
- Update workflow examples with the unified CLI.

- [ ] **Step 2: Run harness adapter generator to sync all panels**

Run: `uv run python tools/sync_harness_adapters.py`
Expected: Regenerates root `AGENTS.md`, `CLAUDE.md`, and all harness skill definitions (`ag-*`, `cc-*`, `oc-*`, `codex-*`).

- [ ] **Step 3: Run `--check` to verify no drift**

Run: `uv run python tools/sync_harness_adapters.py --check`
Expected: PASS ("all generated adapters are current").

- [ ] **Step 4: Run full test suite and linters**

Run:
```powershell
$env:PYTHONUTF8=1; $env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run pytest -q
uv run ruff check src tests main.py tools/sync_harness_adapters.py
uv run ruff format --check src tests main.py tools/sync_harness_adapters.py
```
Expected: All tests pass, Ruff check clean.

- [ ] **Step 5: Commit**

```bash
git add .harness/source/ README.md ARCHITECTURE.md AGENTS.md CLAUDE.md .agents/ .agent/ .claude/
git commit -m "docs: synchronize documentation and harness adapters for unified orchestrator CLI"
```

---

### Task 9: Disposable-Slug Live Smoke Check Script

**Files:**
- Create: `tests/smoke/run_disposable_smoke.py`

- [ ] **Step 1: Write disposable live smoke test script**

Implement `tests/smoke/run_disposable_smoke.py` that:
1. Generates a unique disposable slug: `f"smoke-live-{uuid.uuid4().hex[:8]}"`.
2. Verifies `agy.exe`, `ebook-convert`, and `epubcheck.jar` are available on the system.
3. Invokes the unified orchestrator CLI:
   `uv run python main.py orchestrate --url "https://www.piaotia.com/html/15/15305/" --slug <disposable-slug> --style tien_hiep --limit 3 --formats epub,pdf --yes`
4. Inspects outputs:
   - `books/<disposable-slug>/reports/source-scope.yaml` exists with `selected_count: 3`.
   - `books/<disposable-slug>/translations/0001-1.txt`, `0002-2.txt`, `0003-3.txt` exist.
   - `books/<disposable-slug>/exports/<slug>.epub` and `.pdf` exist and size > 0.
5. Cleans up only the disposable workspace upon completion. Never touches `books/tien-phu-truong-sinh`.

- [ ] **Step 2: Run dry-run / integration check of smoke script**

Run: `uv run python tests/smoke/run_disposable_smoke.py --help`
Expected: Displays usage.

- [ ] **Step 3: Commit**

```bash
git add tests/smoke/run_disposable_smoke.py
git commit -m "test(smoke): add disposable slug live smoke test script for unified orchestrator CLI"
```
