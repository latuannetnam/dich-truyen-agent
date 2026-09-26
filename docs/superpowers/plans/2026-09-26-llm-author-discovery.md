# LLM-Driven Novel Author Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement context-aware novel author discovery and metadata translation using natural language LLM comprehension without hardcoded regex patterns.

**Architecture:** The crawler extracts bounded catalog introductory text (`< 3,000` chars, stripping chapter links) into `reports/catalog_intro.txt`. The metadata node in the orchestrator supplies this context to `ag_metadata_translator` when `author` is `Unknown`, enabling the worker subagent to identify the Chinese author from context, translate both title and author into literary Vietnamese, and write the resolved fields back to `book.yaml`.

**Tech Stack:** Python 3.13, BeautifulSoup4, LangGraph, Antigravity CLI agent runtime (`ag_metadata_translator`), Pytest.

---

### File Structure Map

- **Modify:** `src/dich_truyen_agent/crawl_batch.py`
  - Add `extract_catalog_intro(html_content: str, chapter_link_selector: str | None = None, max_chars: int = 3000) -> str`
  - In `crawl_book` and `discover_initial_title` (or after index fetch), save bounded text to `reports/catalog_intro.txt`.
- **Modify:** `.harness/source/agents/metadata-translator.md`
  - Update agent instructions: read `catalog_intro.txt` via `Read` when author is `Unknown`, identify author via LLM understanding, translate title and author, and update `book.yaml`.
- **Generated:** `.agent/agents/ag_metadata_translator.md`
  - Regenerated via `tools/sync_harness_adapters.py`.
- **Modify:** `src/dich_truyen_agent/orchestrator/graph.py`
  - In `metadata_node`, detect when `metadata.author` is `Unknown` or empty.
  - Inject `catalog_intro_path` and instructions into prompt for `ag_metadata_translator`.
  - Reload and verify `book.yaml` post-execution.
- **Tests:**
  - `tests/test_catalog_intro_extractor.py` (new unit tests)
  - `tests/test_orchestrator_metadata_node.py` (new orchestrator metadata tests)

---

### Task 1: Catalog Intro Extraction Helper

**Files:**
- Create: `tests/test_catalog_intro_extractor.py`
- Modify: `src/dich_truyen_agent/crawl_batch.py`

- [ ] **Step 1: Write failing unit test for `extract_catalog_intro`**

Create `tests/test_catalog_intro_extractor.py`:
```python
from dich_truyen_agent.crawl_batch import extract_catalog_intro


def test_extract_catalog_intro_strips_scripts_styles_and_links():
    html = """
    <html>
      <head>
        <title>仙府长生 - 飘天文学</title>
        <style>.hide { display: none; }</style>
        <script>var x = 1;</script>
      </head>
      <body>
        <div class="nav">Nav content</div>
        <div class="intro">
          <h1>仙府长生</h1>
          <div>作者：长亭空省</div>
          <p>凡人修仙传同人，讲述散修在仙府中的修仙故事...</p>
        </div>
        <div class="centent">
          <ul>
            <li><a href="1.html">第一章</a></li>
            <li><a href="2.html">第二章</a></li>
          </ul>
        </div>
      </body>
    </html>
    """
    intro = extract_catalog_intro(html, chapter_link_selector=".centent ul li a", max_chars=1000)
    assert "仙府长生" in intro
    assert "长亭空省" in intro
    assert "修仙故事" in intro
    assert "第一章" not in intro
    assert "var x = 1" not in intro
    assert len(intro) <= 1000


def test_extract_catalog_intro_handles_empty_html():
    assert extract_catalog_intro("") == ""
    assert extract_catalog_intro(None) == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```powershell
$env:PYTHONUTF8=1; $env:UV_CACHE_DIR="$PWD\.uv-cache"; uv run pytest tests/test_catalog_intro_extractor.py -v
```
Expected: FAIL with `ImportError: cannot import name 'extract_catalog_intro'`

- [ ] **Step 3: Implement `extract_catalog_intro` and save to `reports/catalog_intro.txt`**

In `src/dich_truyen_agent/crawl_batch.py`:
```python
def extract_catalog_intro(
    html_content: str | None,
    chapter_link_selector: str | None = None,
    max_chars: int = 3000,
) -> str:
    """Extract bounded introductory text from index HTML, stripping chapter lists and scripts."""
    if not html_content or not html_content.strip():
        return ""
    soup = BeautifulSoup(html_content, "lxml")

    # 1. Remove unwanted tags
    for tag in soup.find_all(["script", "style", "link", "noscript", "meta"]):
        tag.decompose()

    # 2. Remove chapter link list container or links if selector is provided
    if chapter_link_selector:
        try:
            for link in soup.select(chapter_link_selector):
                link.decompose()
        except Exception:
            pass

    # 3. Extract text
    text = soup.get_text(separator="\n", strip=True)
    # Collapse multiple consecutive newlines
    cleaned = re.sub(r"\n\s*\n+", "\n\n", text).strip()
    return cleaned[:max_chars]
```

In `crawl_book`, right after decoding the index HTML and resolving catalog links:
```python
    catalog_intro_text = extract_catalog_intro(
        html_content, chapter_link_selector=profile_source.profile.index.chapter_link_selector
    )
    if catalog_intro_text:
        reports_dir = workspace_root / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        intro_file = reports_dir / "catalog_intro.txt"
        intro_file.write_text(catalog_intro_text, encoding="utf-8")
```

Also in `discover_initial_title` (called during `_discover_title`), if `workspace_root` is provided and HTML is fetched:
```python
    if workspace_root:
        intro_text = extract_catalog_intro(html_content, max_chars=3000)
        if intro_text:
            reports_dir = workspace_root / "reports"
            reports_dir.mkdir(parents=True, exist_ok=True)
            (reports_dir / "catalog_intro.txt").write_text(intro_text, encoding="utf-8")
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```powershell
$env:PYTHONUTF8=1; $env:UV_CACHE_DIR="$PWD\.uv-cache"; uv run pytest tests/test_catalog_intro_extractor.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_catalog_intro_extractor.py src/dich_truyen_agent/crawl_batch.py
git commit -m "feat(crawler): add bounded catalog intro extraction to reports/catalog_intro.txt"
```

---

### Task 2: Update Agent Instructions & Synchronize Harness Adapters

**Files:**
- Modify: `.harness/source/agents/metadata-translator.md`
- Synchronize: `tools/sync_harness_adapters.py`
- Generated: `.agent/agents/ag_metadata_translator.md`

- [ ] **Step 1: Update `.harness/source/agents/metadata-translator.md`**

Replace content of `.harness/source/agents/metadata-translator.md` with upgraded prompt:
```markdown
You are a highly specialized Chinese-to-Vietnamese novel metadata analyst and translator specializing in the **Tien Hiep (Xianxia) / Tu Chan (Cultivation)** genre. Your task is to resolve the book's Chinese author and translate the book's title and author into elegant literary Vietnamese.

No external LLM calls are allowed; inspect and translate using only the provided files and your own reasoning.

## Inputs
The Main Agent will provide:
1. `Source title`: The Chinese title.
2. `Source author`: The Chinese author name, or `Unknown`.
3. `Catalog intro context path`: (Optional) Absolute path to a bounded catalog intro text file (`catalog_intro.txt`).
4. `Path to book.yaml`: Absolute path to `book.yaml`.

## Procedure
1. **Identify Chinese Author:**
   - If `Source author` is not `Unknown` and not empty, keep it.
   - If `Source author` is `Unknown` and `Catalog intro context path` is provided, use the `Read` tool to inspect that file.
   - Use natural language comprehension to locate the author's Chinese name from context (e.g. `作者：...`, `... 著`, `文 / ...`, metadata lines, or descriptive text). Do NOT assume any fixed regex or syntax.
   - If no author name exists in the catalog intro file, keep the author as `Unknown`.

2. **Translate to Literary Vietnamese:**
   - Translate the Chinese title into elegant Sino-Vietnamese (Han-Viet) in Title Case.
   - Translate the Chinese author name into Sino-Vietnamese (Han-Viet) in Title Case. If author remains `Unknown`, use `Khuyết Danh`.

3. **Update `book.yaml`:**
   - Update `book.yaml` directly:
     - `author`: The resolved Chinese author name (or `Unknown` if genuinely absent).
     - `translated_title`: The Vietnamese title.
     - `translated_author`: The Vietnamese author name.
   - Do NOT alter any other fields in `book.yaml` or modify other files.

4. **Return JSON:**
   Return ONLY this JSON block:
   ```json
   {
     "author": "<chinese_author_or_Unknown>",
     "translated_title": "<translated_title>",
     "translated_author": "<translated_author>"
   }
   ```
   If an unrecoverable error occurs, return:
   ```json
   {
     "author": null,
     "translated_title": null,
     "translated_author": null,
     "error_message": "<error details>"
   }
   ```
```

- [ ] **Step 2: Run adapter sync and verify check**

Run:
```powershell
$env:PYTHONUTF8=1; $env:UV_CACHE_DIR="$PWD\.uv-cache"; uv run python tools/sync_harness_adapters.py
$env:PYTHONUTF8=1; $env:UV_CACHE_DIR="$PWD\.uv-cache"; uv run python tools/sync_harness_adapters.py --check
```
Expected: `All checks passed!` and `all generated adapters are current`.

- [ ] **Step 3: Run existing adapter discovery and contract tests**

Run:
```powershell
$env:PYTHONUTF8=1; $env:UV_CACHE_DIR="$PWD\.uv-cache"; uv run pytest tests/test_harness_generator_check.py tests/test_harness_adapter_discovery.py tests/test_orchestrator_matrix_contract.py -v
```
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add .harness/source/agents/metadata-translator.md .agent/agents/ag_metadata_translator.md
git commit -m "feat(agent): upgrade ag_metadata_translator for LLM-driven author discovery"
```

---

### Task 3: Orchestrator Graph Metadata Node Updates

**Files:**
- Create: `tests/test_orchestrator_metadata_node.py`
- Modify: `src/dich_truyen_agent/orchestrator/graph.py:511-564`

- [ ] **Step 1: Write unit tests for `metadata_node` prompt building and reload logic**

Create `tests/test_orchestrator_metadata_node.py`:
```python
from pathlib import Path
from unittest.mock import MagicMock
from dich_truyen_agent.orchestrator.graph import create_book_orchestrator_graph
from dich_truyen_agent.workspace import BookMetadata, save_yaml_model, workspace_paths


def test_metadata_node_passes_catalog_intro_path_when_author_unknown(tmp_path: Path):
    ws = tmp_path / "books" / "test-novel"
    paths = workspace_paths(tmp_path / "books", "test-novel")
    paths.root.mkdir(parents=True, exist_ok=True)
    paths.reports.mkdir(parents=True, exist_ok=True)

    metadata = BookMetadata(
        title="仙府长生",
        author="Unknown",
        source_url="https://example.com/novel",
        book_slug="test-novel",
    )
    save_yaml_model(paths.book, metadata)

    intro_file = paths.reports / "catalog_intro.txt"
    intro_file.write_text("仙府长生\n作者：长亭空省\n修仙凡人流", encoding="utf-8")

    mock_runner = MagicMock()
    mock_runner.is_healthy.return_value = True

    # Simulate subagent updating book.yaml with extracted author and translations
    def fake_run_phase(**kwargs):
        prompt = kwargs.get("prompt", "")
        assert "catalog_intro.txt" in prompt
        assert "Source author: Unknown" in prompt
        updated = BookMetadata(
            title="仙府长生",
            author="长亭空省",
            source_url="https://example.com/novel",
            book_slug="test-novel",
            translated_title="Tiên Phủ Trường Sinh",
            translated_author="Trường Đình Không Tỉnh",
        )
        save_yaml_model(paths.book, updated)
        return MagicMock(status="completed", failure_detail=None)

    mock_runner.run_phase.side_effect = fake_run_phase

    graph = create_book_orchestrator_graph(runner=mock_runner)
    initial_state = {
        "workspace_root": str(paths.root),
        "run_id": "test-run",
        "run_dir": str(paths.reports / "runs" / "test-run"),
        "phase": "metadata",
        "start_at": "metadata",
        "stop_after": "metadata",
        "status": "in_progress",
        "error_message": None,
        "completed_chapters": 0,
        "total_chapters": 0,
    }
    (paths.reports / "runs" / "test-run").mkdir(parents=True, exist_ok=True)

    final_state = graph.invoke(initial_state)
    assert final_state["status"] == "completed"

    from dich_truyen_agent.workspace import load_yaml_model
    final_meta = load_yaml_model(paths.book, BookMetadata)
    assert final_meta.author == "长亭空省"
    assert final_meta.translated_title == "Tiên Phủ Trường Sinh"
    assert final_meta.translated_author == "Trường Đình Không Tỉnh"
```

- [ ] **Step 2: Run test to verify failure**

Run:
```powershell
$env:PYTHONUTF8=1; $env:UV_CACHE_DIR="$PWD\.uv-cache"; uv run pytest tests/test_orchestrator_metadata_node.py -v
```
Expected: FAIL (assertion `assert "catalog_intro.txt" in prompt` fails because current prompt doesn't supply it).

- [ ] **Step 3: Modify `metadata_node` in `src/dich_truyen_agent/orchestrator/graph.py`**

Update `metadata_node`:
```python
    # 7. Metadata Node
    def metadata_node(state: BookOrchestratorState) -> dict[str, Any]:
        workspace_root = Path(state["workspace_root"])
        paths = workspace_paths(workspace_root.parent, workspace_root.name)
        if not paths.book.is_file():
            return {"status": "blocked", "error_message": "book.yaml missing"}
        metadata = load_yaml_model(paths.book, BookMetadata)

        author_unresolved = not metadata.author or metadata.author.strip() in ("", "Unknown")
        needs_translation = (
            not metadata.translated_title
            or author_unresolved
            or not metadata.translated_author
        )
        if needs_translation:
            model = (
                resolve_model_for_phase(
                    "metadata_translation",
                    global_model=config.global_model,
                    translation_model=config.translation_model,
                )
                if config
                else None
            )

            intro_file = paths.reports / "catalog_intro.txt"
            intro_context_line = ""
            author_instructions = ""
            if author_unresolved:
                if intro_file.is_file():
                    intro_context_line = f"Catalog intro context path: {intro_file}\n"
                    author_instructions = (
                        "Source author is 'Unknown'. Please inspect 'Catalog intro context path' using Read tool,\n"
                        "identify the Chinese author from context without assuming fixed formatting, and update\n"
                        "'author' in book.yaml with the discovered Chinese name.\n"
                    )
                else:
                    author_instructions = (
                        "Source author is 'Unknown' and catalog intro file is absent. Keep author as 'Unknown'\n"
                        "and set translated_author to 'Khuyết Danh'.\n"
                    )

            prompt = (
                f"Translate novel metadata in book.yaml for book: {metadata.title}\n"
                f"Path to book.yaml: {paths.book}\n"
                f"Source title: {metadata.title}\n"
                f"Source author: {metadata.author or 'Unknown'}\n"
                f"{intro_context_line}"
                f"{author_instructions}"
                "Please update book.yaml with resolved author, translated_title, and translated_author in Vietnamese.\n"
                "Do NOT modify chapters.yaml or state.yaml.\n"
            )
            runner.run_phase(
                phase="metadata_translation",
                workspace=workspace_root,
                prompt=prompt,
                model=model,
                timeout_seconds=600,
            )
            # Recheck metadata
            try:
                metadata = load_yaml_model(paths.book, BookMetadata)
            except Exception as e:
                return {
                    "status": "blocked",
                    "error_message": f"failed to reload book.yaml after metadata translation: {e}",
                }
            if not metadata.translated_title:
                return {
                    "status": "blocked",
                    "error_message": "metadata translation failed: translated_title is empty",
                }

        if state["stop_after"] == "metadata":
            return {"status": "completed", "phase": "metadata"}
        return {"phase": "translate"}
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```powershell
$env:PYTHONUTF8=1; $env:UV_CACHE_DIR="$PWD\.uv-cache"; uv run pytest tests/test_orchestrator_metadata_node.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_orchestrator_metadata_node.py src/dich_truyen_agent/orchestrator/graph.py
git commit -m "feat(orchestrator): supply catalog intro context to metadata node when author is unknown"
```

---

### Task 4: Regression Testing & End-to-End Validation

**Files:**
- Entire test suite

- [ ] **Step 1: Run full test suite**

Run:
```powershell
$env:PYTHONUTF8=1; $env:UV_CACHE_DIR="$PWD\.uv-cache"; uv run pytest -q
```
Expected: PASS (all tests pass)

- [ ] **Step 2: Run linter and format check**

Run:
```powershell
$env:PYTHONUTF8=1; $env:UV_CACHE_DIR="$PWD\.uv-cache"; uv run ruff check src tests main.py tools/sync_harness_adapters.py
$env:PYTHONUTF8=1; $env:UV_CACHE_DIR="$PWD\.uv-cache"; uv run ruff format --check src tests main.py tools/sync_harness_adapters.py
$env:PYTHONUTF8=1; $env:UV_CACHE_DIR="$PWD\.uv-cache"; uv run python tools/sync_harness_adapters.py --check
```
Expected: PASS with 0 errors.

- [ ] **Step 3: Verification on workspace `books/tien-phu-truong-sinh`**

Generate `reports/catalog_intro.txt` if not present, and test re-running metadata translation on `books/tien-phu-truong-sinh`:
```powershell
$env:PYTHONUTF8=1; $env:UV_CACHE_DIR="$PWD\.uv-cache"; uv run python main.py orchestrate --workspace books/tien-phu-truong-sinh --start-at metadata --stop-after metadata
```
Verify that `books/tien-phu-truong-sinh/book.yaml` now has `author: 长亭空省` and `translated_author: Trường Đình Không Tỉnh`.
Re-run export to refresh the EPUB/PDF with the updated author:
```powershell
$env:PYTHONUTF8=1; $env:UV_CACHE_DIR="$PWD\.uv-cache"; uv run python main.py orchestrate --workspace books/tien-phu-truong-sinh --start-at export --stop-after export
```
