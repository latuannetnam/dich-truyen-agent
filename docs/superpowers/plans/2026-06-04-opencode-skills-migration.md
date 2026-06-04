# OpenCode-Native Skills Migration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the four novel-translation pipeline skills (`crawl-book`, `translate-book`, `check-translation`, `export-book`) plus the `translator` subagent to OpenCode-native form, **without modifying** the existing `.agent/skills/*` or `.claude/skills/*` originals. Replace the Claude PreToolUse hook with a declarative `permission.bash` guardrail in `opencode.json`.

**Architecture:** Six new files under `.opencode/` (4 skill mirrors + 1 subagent + 1 spec already written). Two existing files get additive edits (`opencode.json` and `AGENTS.md`). Four small pytest files in `tests/` enforce the contract. TDD throughout: write the failing test first, see it fail, implement, see it pass, commit.

**Tech Stack:** Python 3.11+, pytest, OpenCode skill loader, OpenCode permission system, Git, PowerShell (Windows). No new runtime dependencies.

**Spec:** `docs/superpowers/specs/2026-06-04-opencode-skills-migration-design.md`

**Reference originals (DO NOT MODIFY):**
- `.agent/skills/{crawl-book,translate-book,check-translation,export-book}/SKILL.md`
- `.claude/skills/{crawl-book,translate-book,check-translation,export-book}/SKILL.md`
- `.claude/agents/translator.md`
- `.claude/hooks/check_external_llm.py`

---

## File Structure (created or modified by this plan)

| File | Action | Task |
|---|---|---|
| `.opencode/skill/oc-crawl-book/SKILL.md` | create | T1 |
| `.opencode/skill/oc-translate-book/SKILL.md` | create | T1 |
| `.opencode/skill/oc-check-translation/SKILL.md` | create | T1 |
| `.opencode/skill/oc-export-book/SKILL.md` | create | T1 |
| `.opencode/agent/oc-translator.md` | create | T2 |
| `opencode.json` | modify (additive) | T3 |
| `AGENTS.md` | modify (append) | T4 |
| `tests/test_oc_skills_discoverable.py` | create | T1 |
| `tests/test_oc_translator_frontmatter.py` | create | T2 |
| `tests/test_opencode_json_valid.py` | create | T3 |
| `tests/test_ag_md_references.py` | create | T4 |

---

## Task 1: Create the four `oc-*` skill files (TDD)

**Files:**
- Create: `tests/test_oc_skills_discoverable.py`
- Create: `.opencode/skill/oc-crawl-book/SKILL.md`
- Create: `.opencode/skill/oc-translate-book/SKILL.md`
- Create: `.opencode/skill/oc-check-translation/SKILL.md`
- Create: `.opencode/skill/oc-export-book/SKILL.md`

- [ ] **Step 1.1: Write the failing test**

Create `tests/test_oc_skills_discoverable.py` with this content:

```python
"""Verify OpenCode-native skills are discoverable with valid frontmatter."""
from pathlib import Path
import re

import pytest

OC_SKILLS_DIR = Path(__file__).parent.parent / ".opencode" / "skill"

EXPECTED_SKILLS = [
    "oc-crawl-book",
    "oc-translate-book",
    "oc-check-translation",
    "oc-export-book",
]


def _parse_frontmatter(skill_md: Path) -> str:
    content = skill_md.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    assert match, f"No YAML frontmatter in {skill_md}"
    return match.group(1)


@pytest.mark.parametrize("skill_name", EXPECTED_SKILLS)
def test_skill_directory_exists(skill_name):
    skill_dir = OC_SKILLS_DIR / skill_name
    assert skill_dir.is_dir(), f"Missing skill directory: {skill_dir}"


@pytest.mark.parametrize("skill_name", EXPECTED_SKILLS)
def test_skill_md_exists(skill_name):
    skill_md = OC_SKILLS_DIR / skill_name / "SKILL.md"
    assert skill_md.is_file(), f"Missing SKILL.md: {skill_md}"


@pytest.mark.parametrize("skill_name", EXPECTED_SKILLS)
def test_skill_frontmatter_name_matches_folder(skill_name):
    skill_md = OC_SKILLS_DIR / skill_name / "SKILL.md"
    fm = _parse_frontmatter(skill_md)
    name_match = re.search(r"^name:\s*([\w-]+)", fm, re.MULTILINE)
    assert name_match, f"Missing 'name' in frontmatter of {skill_md}"
    assert name_match.group(1) == skill_name, (
        f"name '{name_match.group(1)}' does not match folder '{skill_name}'"
    )


@pytest.mark.parametrize("skill_name", EXPECTED_SKILLS)
def test_skill_frontmatter_description_uses_use_when(skill_name):
    skill_md = OC_SKILLS_DIR / skill_name / "SKILL.md"
    fm = _parse_frontmatter(skill_md)
    desc_match = re.search(r'^description:\s*["\']?(.+?)["\']?$', fm, re.MULTILINE)
    assert desc_match, f"Missing 'description' in frontmatter of {skill_md}"
    desc = desc_match.group(1).strip().strip("\"'")
    assert "Use when" in desc or "use when" in desc, (
        f"description should mention 'Use when' in {skill_md}, got: {desc!r}"
    )
```

- [ ] **Step 1.2: Run test to verify it fails**

Run:
```powershell
$env:PYTHONUTF8=1; uv run pytest tests/test_oc_skills_discoverable.py -q
```

Expected: 16 failures (4 skills × 4 tests), all "Missing skill directory" / "Missing SKILL.md" / "No YAML frontmatter".

- [ ] **Step 1.3: Create the 4 skill files**

Create each of the 4 SKILL.md files. Frontmatter + adapted body. Each file MUST start with the exact `---` frontmatter block (name, description). The body adapts the Claude mirror content for OpenCode (lowercase tool names, `task()` instead of `Agent({subagent_type})`).

**File 1: `.opencode/skill/oc-crawl-book/SKILL.md`**

```markdown
---
name: oc-crawl-book
description: "Use when crawling a Chinese novel into a validated local workspace and securing a crawl-approved checkpoint. OpenCode-native mirror of the crawl-book skill; uses the lowercase bash tool and read tool. Triggered by phrases like 'crawl this novel', 'download chapters', 'start a new book crawl', or when a workspace lacks the crawl-approved gate."
---

# OC-Crawl Book

Crawl a Chinese novel sequentially and resume downloads into a local workspace using robust static parsing and headless browser fallback. This is the OpenCode-native mirror of `.claude/skills/crawl-book/SKILL.md` — same CLI commands, adapted for the OpenCode runtime (`bash` tool, `read` tool, PowerShell on Windows).

## Workflow

1. **Initialize or Resume Crawl**:
   Execute the deterministic crawl helper via the `bash` tool:
   ```powershell
   $env:PYTHONUTF8=1
   uv run python main.py crawl-book --books-root books --slug <book-slug> --source-url <source-url> [--style <style-name>] [--max-chapters <limit>] [--chapter-delay-seconds <delay>]
   ```
   - Defaults: `--max-chapters 0` (unlimited), `--chapter-delay-seconds 3.0` (polite pacing).
   - This discovers the complete catalog in `chapters.yaml` and downloads raw text chapters to `raw/`.
   - On exit, it writes a compact result file under `reports/results/crawl-book.yaml`.

2. **Handle Profile Validation & Repair**:
   If catalog discovery or chapter extraction fails due to dynamic JavaScript rendering:
   - Check if a local override `crawl-profile.yaml` exists in the workspace.
   - If not, create one to override selectors or enable lazy browser fallback.
   - Validate and test the override:
     ```powershell
     $env:PYTHONUTF8=1
     uv run python main.py validate-crawl-profile --workspace books/<book-slug> --profile books/<book-slug>/crawl-profile.yaml
     ```
   - Promote the local override to shared templates if appropriate:
     ```powershell
     $env:PYTHONUTF8=1
     uv run python main.py promote-crawl-profile --workspace books/<book-slug>
     ```

3. **Verify and Audit the Report**:
   Inspect the structured crawl report written under `reports/crawl.yaml` using the `read` tool.
   - Verify completed, discovered, and failed counts.
   - Review warning residue findings or chapter length anomalies.

4. **Approve Crawl**:
   Create a hash-backed, scope-aware `crawl-approved` checkpoint:
   ```powershell
   $env:PYTHONUTF8=1
   uv run python main.py approve-crawl --workspace books/<book-slug> [--max-chapters <limit>]
   ```
   - Approval evidence will cover `reports/crawl.yaml` and every raw file in download scope.
   - The checkpoint is saved under `checkpoints/crawl-approved.yaml` and is verified by downstream phases.

## Notes for OpenCode Runtime

- Use the **`bash` tool** (not the Claude `Bash`) to execute CLI commands.
- Use the **`read` tool** to inspect `reports/crawl.yaml`, `chapters.yaml`, and `state.yaml`.
- Do NOT read raw Chinese chapter files (`books/<book-slug>/raw/*.txt`) into your main context — they overflow the window. Trust the CLI report summaries.
- The `permission.bash` rules in `opencode.json` block any bash command that references banned external LLM endpoints, env vars, or import patterns (declarative guardrail, replaces the Claude PreToolUse hook).
```

**File 2: `.opencode/skill/oc-translate-book/SKILL.md`**

```markdown
---
name: oc-translate-book
description: "Use when translating an approved Chinese novel workspace sequentially into Vietnamese, chapter by chapter. OpenCode-native mirror of the translate-book skill; uses task({subagent_type:'oc-translator'}) for subagent dispatch and embeds the sequential loop in the skill body (no Workflow tool). Triggered by phrases like 'translate book', 'translate next chapters', 'continue translation', 'resume translating <book>', or when a workspace has a valid crawl-approved checkpoint but pending Vietnamese chapters."
---

# OC-Translate Book (Sequential Subagent Orchestration — OpenCode)

## Overview

Translate crawled and approved Chinese chapters **strictly in sequential order** by dispatching the locked-down `oc-translator` subagent (see [.opencode/agent/oc-translator.md](../../agent/oc-translator.md)) one chapter at a time. The Main Agent is a lightweight coordinator: it queries CLI commands, dispatches the subagent via `task()`, verifies the staging output, and atomically promotes the result. Raw text files and full translations never enter the Main Agent's context.

> [!IMPORTANT]
> **Context Protection & Sequential Execution.**
> Do NOT read raw Chinese files or completed Vietnamese chapters in your own context. The `oc-translator` subagent is the only worker that reads them.
> Chapters are translated strictly in order — `N+1` starts only after `N` is promoted. No overlap.

> [!WARNING]
> **External LLM API Prohibition.**
> Translation must go through `task({subagent_type: "oc-translator", ...})` — never via Python/curl to OpenAI/OpenRouter/Gemini/DeepSeek/Anthropic. The `permission.bash` rules in `opencode.json` block violating bash commands (declarative, command-string only — no .py file-content scan).

> [!NOTE]
> **No `Workflow` tool in OpenCode.**
> The Claude mirror's `Workflow({name: "translate-book", args: {workspace}})` orchestrator does NOT have an OpenCode equivalent. The sequential loop is embedded directly in this skill body as Steps 1–8. The agent uses its own judgment to continue looping after each successful `promote-chapter`, or to stop if invoked for a single chapter.

---

## Core Workflow

All CLI commands run through the `bash` tool with `$env:PYTHONUTF8=1` (PowerShell on Windows).

### Step 1 — Verify the crawl gate
```powershell
$env:PYTHONUTF8=1
uv run python main.py check-gate --workspace books/<book-slug> --type crawl-approved
```
If this blocks or fails, stop and ask the user to approve the crawl first.

### Step 2 — Query next pending chapter
```powershell
$env:PYTHONUTF8=1
uv run python main.py show-translation-progress --workspace books/<book-slug>
```
Parse the JSON in the `reason` field:
- `completed` → announce success, stop.
- `blocked` → report the gap and stop.
- `pending` → extract `chapter_id`, `slug`, `original_title`.

### Step 3 — Fetch translation context
```powershell
$env:PYTHONUTF8=1
uv run python main.py prepare-translation-context --workspace books/<book-slug> --chapter-id <chapter_id>
```
Parse the JSON for: `raw_path`, `style_path`, `glossary_path`, `prev_translation_path` (or `null`), `is_fallback`, `fallback_reason`.

### Step 4 — Resolve absolute paths
The subagent runs with its own cwd, so absolute paths are mandatory. Use Python `pathlib.Path(...).resolve()` to convert the four input paths plus:
- `staged_txt`: `<project_root>\books\<book-slug>\staging\chuong-{chapter_id:04d}-staged.txt`
- `staged_yaml`: `<project_root>\books\<book-slug>\staging\chuong-{chapter_id:04d}-proposals.yaml`

### Step 5 — Dispatch the oc-translator subagent
The `oc-translator` subagent's system prompt (`.opencode/agent/oc-translator.md`) is the single source of truth for the title rule, lexical sandbox, glossary precedence, archaic tone, no-Chinese-residue rule, and the JSON return contract. Your dispatch prompt only passes per-chapter parameters — do **not** restate the rules.

```python
task(
  subagent_type="oc-translator",
  description="Translate chapter <chapter_id>",
  prompt="<see template below>"
)
```

**Dispatch prompt template (~20 lines, parameters only):**

```markdown
You are translating chapter <chapter_id> of a Chinese xianxia novel into Vietnamese.

## Inputs (absolute paths)
1. **Raw Chinese Text:** Read `<raw_path>`
2. **Style Guidelines:** Read `<style_path>` (archaic tone)
3. **Glossary:** Read `<glossary_path>` (glossary mappings override your own rendering)
4. **Previous Chapter Context:** Read `<prev_translation_path>` for pronoun (xưng hô) continuity.
   (If null: this is Chapter 1 or a fallback — reason: <fallback_reason>. Translate without predecessor context.)

## Output paths (absolute)
- staged_txt:  `<staged_txt>`
- staged_yaml: `<staged_yaml>` (write only if you have new glossary proposals)

## Reminders (full rules in your system prompt)
- Title: `第[N]章` → `Chương [N]`; Sino-Vietnamese Title Case; single space joiner; no colon/hyphen/brackets.
- File: line 1 = `# [title_vi]`, line 2 blank, line 3+ body.
- Lexical Sandbox: scan for banned English helper words per your system prompt table.
- No Chinese characters in the body. Proposals go ONLY in staged_yaml.

## Return
Return ONLY the success or error JSON block defined in your system prompt. Nothing else.

chapter_id = <chapter_id>.
```

### Step 6 — Verify staging output (lightweight)
Use `read` with `limit: 3` on `staged_txt`. Confirm:
- Line 1 starts with `# Chương <chapter_id>` (number matches).
- Line 2 is blank.
- File is non-empty; character count is in the ballpark of the subagent's reported count.

### Step 7 — Promote atomically
```powershell
$env:PYTHONUTF8=1
uv run python main.py promote-chapter --workspace books/<book-slug> --chapter-id <chapter_id>
```
Confirm `status: ok`. This validates staging, moves the translation into `translations/`, merges any staged glossary proposals, updates `state.yaml` hashes, and cleans up staging files.

### Step 8 — Retry / halt / loop
- **Retry:** On subagent error or promote failure, retry up to **3 times** with a 5s backoff (`Start-Sleep -Seconds 5`).
- **Halt:** If 3 attempts fail, stop immediately and report. The workspace remains clean at the last promoted chapter.
- **Loop:** On success, the agent decides whether to return to Step 2 (next chapter) or stop. There is no automatic orchestrator in OpenCode.

---

## Common Pitfalls

- **Reading raw or completed chapters yourself** — Floods your context. The oc-translator subagent owns all file reads.
- **Restating translation rules in the dispatch prompt** — Wastes tokens and risks drift from the subagent system prompt. Pass parameters, reference the rules.
- **Manually editing `book.json` or `state.yaml`** — Use the CLI (`promote-chapter`, etc.). Never search/replace metadata by hand.
- **Calling external LLM APIs** — Strictly prohibited. The `permission.bash` rules block it. Always use `task({subagent_type: "oc-translator", ...})`.
- **Translating N+1 before N is promoted** — Violates sequential handoff and corrupts pronoun continuity.

<!--
Honesty contracts for tests:
books/<book-slug>/
reports/results/
not implemented by Phase 1
-->
```

**File 3: `.opencode/skill/oc-check-translation/SKILL.md`**

```markdown
---
name: oc-check-translation
description: "Use when validating completed Vietnamese translations and preparing the QA-approved gate. OpenCode-native mirror of the check-translation skill; uses lowercase bash, read, and edit tools. Triggered by phrases like 'QA the translations', 'check translation quality', 'run translation scan', 'approve QA', or when a workspace has all translations promoted but no qa-approved checkpoint."
---

# OC-Check Translation

Deterministic, non-mutating quality check pipeline evaluating structural consistency, CJK residue, character length ratios, and glossary mapping conflicts. Creating a cryptographically secure `qa-approved` checkpoint unlocks final ebook exports. This is the OpenCode-native mirror of `.claude/skills/check-translation/SKILL.md`.

## Workflow

1. **Run Quality Check Scan**:
   Execute the deterministic validation engine to audit all translated chapters (`bash` tool):
   ```powershell
   $env:PYTHONUTF8=1
   uv run python main.py check-translation --workspace books/<book-slug>
   ```
   - This scan is completely non-mutating and will **never** modify any raw or translated text files.
   - Outputs a detailed findings report to `reports/qa-report.yaml`.
   - Renders a clean Markdown summary table to stdout classifying issues by Category, Chapter, Severity, and details.

2. **Diagnose and Resolve Findings**:
   Inspect findings reported in the terminal or `reports/qa-report.yaml` (use the `read` tool):
   - **Structural Findings:** Fix any missing chapters, empty files, or state inconsistencies in `state.yaml`.
   - **Chinese Residue Warnings:** Highlighted CJK characters or Chinese punctuation marks remaining in Vietnamese text. Manually clean these lines in the translation files using the `edit` tool.
   - **Abnormal Lengths:** Warnings for chapters where the character length ratio relative to raw Chinese is too low (< 0.6) or too high (> 2.0) — indicating truncated prose or repeat output loops.
   - **Glossary Conflicts:** Terms flagged in `reports/glossary-conflicts.yaml`. Manually edit `glossary.yaml` to lock mapping or clear conflict listings.

3. **Approve QA Checkpoint**:
   Once errors are resolved or warnings reviewed, lock and authorize the workspace for export:
   ```powershell
   $env:PYTHONUTF8=1
   uv run python main.py approve-qa --workspace books/<book-slug>
   ```
   - Blocks approval if there are outstanding critical `error` severity findings.
   - Evidence hashing records the checksums of the QA report and every single promoted translation file.
   - Produces the secure `checkpoints/qa-approved.yaml` checkpoint file enabling the downstream export workflows.

## Notes for OpenCode Runtime

- The QA scan is safe to run repeatedly — it never mutates files.
- When manually fixing residue or length issues, edit `books/<book-slug>/translations/chuong-NNNN.txt` directly with the `edit` tool, then re-run the scan.
- Do NOT bulk-read every translation file into your main context. Trust the YAML report summaries.
```

**File 4: `.opencode/skill/oc-export-book/SKILL.md`**

```markdown
---
name: oc-export-book
description: "Use when exporting a QA-approved translation workspace into EPUB/AZW3/MOBI/PDF ebook artifacts. OpenCode-native mirror of the export-book skill; uses the lowercase bash tool. Triggered by phrases like 'export ebook', 'build epub', 'generate the book file', 'compile the novel', or when a workspace has a valid qa-approved checkpoint and needs final artifacts."
---

# OC-Export Book

This skill compiles a sequential, QA-approved translation workspace into conformant canonical EPUB and AZW3 ebook formats by default, and derives MOBI and PDF only if explicitly requested. This is the OpenCode-native mirror of `.claude/skills/export-book/SKILL.md`.

## CLI Usage (bash tool)

```powershell
# Default: generate canonical EPUB + AZW3 only (enforces QA approval checkpoint)
$env:PYTHONUTF8=1
uv run python -m dich_truyen_agent.cli export-book --workspace books/<book-slug>

# Generate EPUB + AZW3 along with optional derivatives (MOBI, PDF)
$env:PYTHONUTF8=1
uv run python -m dich_truyen_agent.cli export-book --workspace books/<book-slug> --formats epub,azw3,mobi,pdf
```

## System Environment Variables

- `DICH_TRUYEN_EPUBCHECK_PATH`: Path to your `epubcheck.jar` file or installation folder. (EPUBCheck is required to validate canonical EPUB compliance before export completes successfully).
- `DICH_TRUYEN_CALIBRE_PATH`: Path to Calibre's `ebook-convert` executable (optional; if missing, derivative format compilation is skipped with a warning, but canonical EPUB generation completes successfully).

Verify these are set via PowerShell:
```powershell
$env:DICH_TRUYEN_EPUBCHECK_PATH
$env:DICH_TRUYEN_CALIBRE_PATH
```

## Outputs

- Canonically compiled EPUB is written atomically to `books/<book-slug>/exports/<book-slug>.epub`.
- Derivative formats are written to the same directory as `books/<book-slug>/exports/<book-slug>.<format>`.
- Export results are logged to `books/<book-slug>/reports/results/export-book.yaml`.

## Notes for OpenCode Runtime

- The export command refuses to run without a valid `qa-approved` checkpoint. If it blocks, run the `oc-check-translation` skill first.
- Use the `read` tool to inspect `reports/results/export-book.yaml` for the per-format success status and any EPUBCheck warnings.
- Do not attempt to validate or modify the resulting `.epub` files by hand — trust the EPUBCheck pipeline.
```

- [ ] **Step 1.4: Run test to verify it passes**

Run:
```powershell
$env:PYTHONUTF8=1; uv run pytest tests/test_oc_skills_discoverable.py -q
```

Expected: 16 passed (4 skills × 4 tests).

- [ ] **Step 1.5: Commit**

```powershell
git add tests/test_oc_skills_discoverable.py .opencode/skill/
git commit -m "feat(opencode): add oc-* skill mirrors for crawl, translate, check, export"
```

---

## Task 2: Create the `oc-translator` subagent (TDD)

**Files:**
- Create: `tests/test_oc_translator_frontmatter.py`
- Create: `.opencode/agent/oc-translator.md`

- [ ] **Step 2.1: Write the failing test**

Create `tests/test_oc_translator_frontmatter.py`:

```python
"""Verify the oc-translator subagent has the right OpenCode frontmatter."""
import re
from pathlib import Path

import pytest

TRANSLATOR_MD = Path(__file__).parent.parent / ".opencode" / "agent" / "oc-translator.md"


@pytest.fixture(scope="module")
def frontmatter() -> str:
    assert TRANSLATOR_MD.is_file(), f"Missing {TRANSLATOR_MD}"
    content = TRANSLATOR_MD.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    assert match, f"No YAML frontmatter in {TRANSLATOR_MD}"
    return match.group(1)


def test_translator_md_exists():
    assert TRANSLATOR_MD.is_file(), f"Missing {TRANSLATOR_MD}"


def test_translator_mode_subagent(frontmatter):
    assert re.search(r"^mode:\s*subagent", frontmatter, re.MULTILINE), (
        "mode must be 'subagent'"
    )


def test_translator_hidden_true(frontmatter):
    assert re.search(r"^hidden:\s*true", frontmatter, re.MULTILINE), (
        "hidden must be true (invoke-only via task())"
    )


def test_translator_bash_tool_disabled(frontmatter):
    assert re.search(r"^  bash:\s*false", frontmatter, re.MULTILINE), (
        "tools.bash must be false"
    )


def test_translator_bash_permission_denied(frontmatter):
    assert re.search(r"^  bash:\s*deny", frontmatter, re.MULTILINE), (
        "permission.bash must be 'deny'"
    )


def test_translator_read_write_glob_grep_enabled(frontmatter):
    for tool in ("read", "write", "glob", "grep"):
        assert re.search(rf"^  {tool}:\s*true", frontmatter, re.MULTILINE), (
            f"tools.{tool} must be true"
        )
```

- [ ] **Step 2.2: Run test to verify it fails**

Run:
```powershell
$env:PYTHONUTF8=1; uv run pytest tests/test_oc_translator_frontmatter.py -q
```

Expected: FAIL on `test_translator_md_exists` (file does not exist yet).

- [ ] **Step 2.3: Create the oc-translator subagent file**

Create `.opencode/agent/oc-translator.md` with this content (frontmatter + body mirrored from `.claude/agents/translator.md`):

```markdown
---
description: "Use when dispatching a single Chinese novel chapter to be translated into Vietnamese with strict Xianxia/Tu Chan (Tiên Hiệp / Tu Chân) style, glossary fidelity, and lexical sandbox enforcement. Dispatch one instance per chapter — never reuse the same instance for multiple chapters, and never use this agent for QA, crawling, or export."
mode: subagent
model: inherit
hidden: true
tools:
  read: true
  write: true
  glob: true
  grep: true
  bash: false
  webfetch: false
  task: false
  edit: false
permission:
  bash: deny
  edit: deny
  webfetch: deny
  task: deny
  websearch: deny
---

You are a highly specialized **Chinese-to-Vietnamese novel translator** specializing in the **Tiên Hiệp (Xianxia) / Tu Chân (Cultivation)** genre. Your sole purpose is to produce a high-quality, professional, elegant Vietnamese translation of a single assigned chapter in literary context. You operate in an isolated context window so the Main Agent (and the orchestrator) stays clean.

## Operating Rules (read once, follow always)

1. **Single chapter only.** You translate exactly one chapter per invocation. Your final response is a JSON return block (schema below) — nothing else.
2. **Tool allowlist:** `read`, `write`, `glob`, `grep` (per frontmatter). You have NO `bash`, NO `webfetch`, NO `task`. Do not request them. If a task seems to require them, fail with status `"error"` and explain.
3. **No external LLM calls.** You never call OpenAI, OpenRouter, Anthropic, Gemini, DeepSeek, or any other API. You translate using only your own reasoning over the input files.
4. **No silent context expansion.** Read only the files the Main Agent's prompt names. Do not browse other chapters, do not enumerate the `translations/` folder, do not glob unrelated paths.
5. **Absolute paths only.** The Main Agent passes resolved absolute paths. Use them verbatim — do not strip the drive letter or rewrite.

## Inputs (the dispatching prompt always provides)

1. **Raw Chinese Text** — `raw_path`
2. **Style Guidelines** — `style_path` (always `archaic` tone unless the file says otherwise)
3. **Glossary** — `glossary_path` (prefer glossary mappings over your own rendering of any term)
4. **Previous Chapter Context** — `prev_translation_path`, or `null` for Chapter 1 / fallback
5. **Output paths** — `staged_txt`, `staged_yaml`
6. **chapter_id** — 1-based sequential integer

## Procedure

### Step 1 — Load inputs
Read the four input files (skipping `prev_translation_path` if null). Use the `read` tool.

### Step 2 — Inspect raw text
Scan the first 500 characters of the raw source for scrambling, anti-scraping paragraphs, or embedded ads. Cleanly parse only the true chapter body.

### Step 3 — Translate the chapter title
- **Number prefix:** `第[N]章` MUST become `Chương [N]`.
- **Body:** Translate remaining characters into Sino-Vietnamese (Hán-Việt) in **Title Case** (e.g. `天魔传说` → `Thiên Ma Truyền Thuyết`).
- **Joiner:** Single space between the number prefix and the title body: `Chương 1715 Thiên Ma Truyền Thuyết`. No colon, no hyphen, no brackets around the chapter number.

### Step 4 — Translate the body
- Produce natural, high-quality literary Vietnamese prose.
- Apply genre guidelines and vocabulary rules from `style_path`.
- Apply glossary mappings from `glossary_path` (these override your own choices).
- Match the pronoun (xưng hô) style of `prev_translation_path` for continuity.
- Maintain the `archaic` tone defined in `style.yaml`.

### Step 5 — Lexical Sandbox Rule (mandatory programmatic scan)
Before writing the file, scan your draft for leaked English helper words and replace them:

| Banned English Word | Vietnamese Equivalent | Notes |
| :--- | :--- | :--- |
| but | nhưng | |
| and | và | |
| or | hoặc | |
| while | trong khi | |
| before | trước khi | |
| after | sau khi | |
| of | của | |
| to | đến / cho | depends on context |
| in | trong | |
| on | trên | |
| at | tại | |
| for | cho / vì | depends on context |
| with | với | |
| the | *(omit article)* | Vietnamese has no articles |
| here | đây | |
| now | bây giờ | |
| okay | được / OK | |

### Step 6 — No Chinese residue in the body
The translated body MUST consist solely of Vietnamese prose. NEVER include raw Chinese characters, bilingual annotations, or translator notes inside the staging translation file. All Chinese term proposals are isolated to the proposals YAML file.

### Step 7 — Write the staged translation
Use `write` to create `staged_txt` exactly:
- Line 1: `# [title_vi]` (e.g. `# Chương 1715 Thiên Ma Truyền Thuyết`)
- Line 2: blank
- Line 3+: chapter body

### Step 8 — Write the staged proposals (only if any)
If you encountered new Chinese names / factions / items / cultivation terms NOT in the glossary and translated them yourself, write `staged_yaml` with this structure:

```yaml
[Chinese Term]:
  translation: "[Vietnamese Mapping]"
  category: "[character|sect|location|item|cultivation|other]"
  note: "[Optional context]"
```

If there are zero proposals, **do not** create the file.

### Step 9 — Self-review
Re-read `staged_txt` (use `read` with `limit: 20` for the head check; full read only if you genuinely need it).

Confirm:
- Line 1 matches `# [title_vi]` exactly.
- No raw Chinese characters anywhere in the body.
- No banned English helper words anywhere in the body.
- File is not empty; character count looks proportional to the raw source.

### Step 10 — Return JSON

**On success — return ONLY this JSON block, nothing before or after:**
```json
{
  "status": "success",
  "chapter_id": <int>,
  "title_vi": "<translated title>",
  "character_count": <int>,
  "proposals_count": <int>
}
```

**On failure — return ONLY this JSON block:**
```json
{
  "status": "error",
  "chapter_id": <int>,
  "title_vi": null,
  "character_count": 0,
  "proposals_count": 0,
  "error_message": "<one-sentence description>"
}
```

Your entire final message MUST be one of these two JSON blocks. No surrounding prose, no markdown commentary, no summaries.
```

- [ ] **Step 2.4: Run test to verify it passes**

Run:
```powershell
$env:PYTHONUTF8=1; uv run pytest tests/test_oc_translator_frontmatter.py -q
```

Expected: 6 passed.

- [ ] **Step 2.5: Commit**

```powershell
git add tests/test_oc_translator_frontmatter.py .opencode/agent/oc-translator.md
git commit -m "feat(opencode): add oc-translator subagent with file-scoped permissions"
```

---

## Task 3: Augment `opencode.json` with `permission.bash` guardrails (TDD)

**Files:**
- Create: `tests/test_opencode_json_valid.py`
- Modify: `opencode.json:1-4` — add `permission` block

- [ ] **Step 3.1: Write the failing test**

Create `tests/test_opencode_json_valid.py`:

```python
"""Verify opencode.json contains the external-LLM guardrail deny rules."""
import json
from pathlib import Path

import pytest

OPENCODE_JSON = Path(__file__).parent.parent / "opencode.json"

DENIED_ENDPOINTS = [
    "api.openai.com",
    "openrouter.ai",
    "api.anthropic.com",
    "generativelanguage.googleapis.com",
    "api.deepseek.com",
]
DENIED_ENV_VARS = [
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "DEEPSEEK_API_KEY",
]
DENIED_IMPORTS = [
    "import openai",
    "import anthropic",
    "from openai",
    "from anthropic",
]
REQUIRED_SAFETY = "rm -rf /*"


@pytest.fixture(scope="module")
def cfg() -> dict:
    assert OPENCODE_JSON.is_file(), f"Missing {OPENCODE_JSON}"
    return json.loads(OPENCODE_JSON.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def bash_rules(cfg) -> dict:
    perm = cfg.get("permission", {})
    bash_rules = perm.get("bash", {})
    assert isinstance(bash_rules, dict), "permission.bash must be an object"
    return bash_rules


def test_opencode_json_exists():
    assert OPENCODE_JSON.is_file()


def test_opencode_json_has_schema(cfg):
    assert cfg.get("$schema") == "https://opencode.ai/config.json"


def test_permission_bash_block_exists(cfg):
    assert "permission" in cfg, "permission block missing"
    assert "bash" in cfg["permission"], "permission.bash block missing"


@pytest.mark.parametrize("endpoint", DENIED_ENDPOINTS)
def test_endpoints_denied(bash_rules, endpoint):
    matches = [p for p in bash_rules if endpoint in p]
    assert matches, f"No deny rule covers endpoint {endpoint!r}"
    assert all(bash_rules[m] == "deny" for m in matches), (
        f"Endpoint {endpoint!r} covered by non-deny rule"
    )


@pytest.mark.parametrize("env_var", DENIED_ENV_VARS)
def test_env_vars_denied(bash_rules, env_var):
    matches = [p for p in bash_rules if env_var in p]
    assert matches, f"No deny rule covers env var {env_var!r}"
    assert all(bash_rules[m] == "deny" for m in matches), (
        f"Env var {env_var!r} covered by non-deny rule"
    )


@pytest.mark.parametrize("imp", DENIED_IMPORTS)
def test_imports_denied(bash_rules, imp):
    matches = [p for p in bash_rules if imp in p]
    assert matches, f"No deny rule covers import {imp!r}"
    assert all(bash_rules[m] == "deny" for m in matches), (
        f"Import {imp!r} covered by non-deny rule"
    )


def test_rm_rf_root_safety(bash_rules):
    assert REQUIRED_SAFETY in bash_rules, f"{REQUIRED_SAFETY!r} safety rule missing"
    assert bash_rules[REQUIRED_SAFETY] == "deny"


def test_broad_allow_base_first(bash_rules):
    """The first rule should be the broad `*` allow; deny rules come after."""
    keys = list(bash_rules.keys())
    assert keys[0] == "*", (
        f"First bash rule must be `*` (broad allow), got: {keys[0]!r}. "
        "opencode evaluates the LAST matching rule, so broad rules must come FIRST."
    )
    assert bash_rules["*"] == "allow", "Base `*` rule must be 'allow'"
```

- [ ] **Step 3.2: Run test to verify it fails**

Run:
```powershell
$env:PYTHONUTF8=1; uv run pytest tests/test_opencode_json_valid.py -q
```

Expected: FAIL on `test_permission_bash_block_exists` (no permission block in current `opencode.json`).

- [ ] **Step 3.3: Augment `opencode.json`**

Read the current `opencode.json` first (currently 4 lines). Replace it with the following content (preserves the existing `plugin` line, adds the `permission` block):

```json
{
  "$schema": "https://opencode.ai/config.json",
  "plugin": ["superpowers@git+https://github.com/obra/superpowers.git"],
  "permission": {
    "bash": {
      "*": "allow",
      "rm -rf /*": "deny",
      "*api.openai.com*": "deny",
      "*openrouter.ai*": "deny",
      "*api.anthropic.com*": "deny",
      "*generativelanguage.googleapis.com*": "deny",
      "*api.deepseek.com*": "deny",
      "*OPENAI_API_KEY*": "deny",
      "*OPENROUTER_API_KEY*": "deny",
      "*ANTHROPIC_API_KEY*": "deny",
      "*GEMINI_API_KEY*": "deny",
      "*DEEPSEEK_API_KEY*": "deny",
      "*import openai*": "deny",
      "*import anthropic*": "deny",
      "*from openai*": "deny",
      "*from anthropic*": "deny"
    },
    "edit": "allow",
    "read": "allow",
    "glob": "allow",
    "grep": "allow",
    "webfetch": "ask",
    "websearch": "ask"
  }
}
```

Use the `edit` tool. The exact `oldString` is the current 4-line file content. The `newString` is the 29-line content above.

- [ ] **Step 3.4: Run test to verify it passes**

Run:
```powershell
$env:PYTHONUTF8=1; uv run pytest tests/test_opencode_json_valid.py -q
```

Expected: All tests pass (5 endpoint tests + 5 env var tests + 4 import tests + safety test + ordering test + 4 structural tests = 20 tests).

- [ ] **Step 3.5: Commit**

```powershell
git add tests/test_opencode_json_valid.py opencode.json
git commit -m "feat(opencode): add permission.bash guardrail for external LLM endpoints"
```

---

## Task 4: Append `AGENTS.md` cross-reference (TDD)

**Files:**
- Create: `tests/test_ag_md_references.py`
- Modify: `AGENTS.md` — append "OpenCode-Native Skill Variants" section

- [ ] **Step 4.1: Write the failing test**

Create `tests/test_ag_md_references.py`:

```python
"""Verify AGENTS.md references the OpenCode-native skills."""
from pathlib import Path

import pytest

AGENTS_MD = Path(__file__).parent.parent / "AGENTS.md"

EXPECTED_REFS = [
    "oc-crawl-book",
    "oc-translate-book",
    "oc-check-translation",
    "oc-export-book",
    "oc-translator",
]


def test_agents_md_exists():
    assert AGENTS_MD.is_file(), f"Missing {AGENTS_MD}"


def test_agents_md_has_opencode_section():
    content = AGENTS_MD.read_text(encoding="utf-8")
    assert "OpenCode-Native Skill Variants" in content, (
        "AGENTS.md is missing the 'OpenCode-Native Skill Variants' section"
    )


@pytest.mark.parametrize("ref", EXPECTED_REFS)
def test_agents_md_references(ref):
    content = AGENTS_MD.read_text(encoding="utf-8")
    assert ref in content, f"AGENTS.md does not mention {ref!r}"
```

- [ ] **Step 4.2: Run test to verify it fails**

Run:
```powershell
$env:PYTHONUTF8=1; uv run pytest tests/test_ag_md_references.py -q
```

Expected: 2 failures minimum — `test_agents_md_has_opencode_section` and 5× `test_agents_md_references`.

- [ ] **Step 4.3: Append the cross-reference section to AGENTS.md**

Use the `edit` tool with `oldString` being the literal last line of the current AGENTS.md (a `---` line) and `newString` being that same line followed by the new section. The exact text to append:

```markdown

## OpenCode-Native Skill Variants

For users running the **OpenCode** runtime (vs. Claude Code or Antigravity), parallel `oc-*` skills live in `.opencode/skill/`:

- `oc-crawl-book` — equivalent of `crawl-book`, uses the `bash` tool
- `oc-translate-book` — equivalent of `translate-book`, uses `task({subagent_type:"oc-translator"})` and embeds the sequential loop in the skill body (no `Workflow` tool)
- `oc-check-translation` — equivalent of `check-translation`
- `oc-export-book` — equivalent of `export-book`
- `oc-translator` (subagent) — equivalent of `.claude/agents/translator.md`

The `.agent/skills/*` and `.claude/skills/*` versions are NOT modified. Both runtimes continue to work. See `opencode.json` `permission.bash` for the OpenCode-specific external-LLM guardrail (declarative, command-string only — Python file-content scan from the original hook is dropped).
```

To find a stable anchor, read the last 5 lines of `AGENTS.md` first, then use that as `oldString`. Verify the file ends with `---` (per the mermaid gate diagram). The append will produce a new H2 section after the final `---`.

- [ ] **Step 4.4: Run test to verify it passes**

Run:
```powershell
$env:PYTHONUTF8=1; uv run pytest tests/test_ag_md_references.py -q
```

Expected: 7 passed (1 exists + 1 section + 5 reference).

- [ ] **Step 4.5: Commit**

```powershell
git add tests/test_ag_md_references.py AGENTS.md
git commit -m "docs: cross-reference OpenCode-native oc-* skills in AGENTS.md"
```

---

## Task 5: Integration verification (all tests together)

**Files:** none (verification only)

- [ ] **Step 5.1: Run the full test suite**

Run:
```powershell
$env:PYTHONUTF8=1; uv run pytest tests/test_oc_skills_discoverable.py tests/test_oc_translator_frontmatter.py tests/test_opencode_json_valid.py tests/test_ag_md_references.py -v
```

Expected: 49 tests passed (16 + 6 + 20 + 7).

- [ ] **Step 5.2: Run the full pre-existing test suite to confirm no regression**

Run:
```powershell
$env:PYTHONUTF8=1; uv run pytest -q
```

Expected: All tests pass (49 new + N pre-existing). If any pre-existing test fails, the migration broke something — investigate before proceeding.

- [ ] **Step 5.3: Verify the originals were not modified**

Run:
```powershell
git diff HEAD~5 -- .agent/skills/ .claude/skills/ .claude/agents/ .claude/hooks/
```

Expected: Empty output. None of the originals should have changed.

- [ ] **Step 5.4: Manual smoke test of the guardrail (informational)**

After exiting plan mode / restarting OpenCode, run via the `bash` tool:
```powershell
python -c "import openai"
```

Expected: Permission denied with reason mentioning the matched pattern. (This is a manual verification — not part of the automated test suite.)

- [ ] **Step 5.5: Final summary commit (only if Step 5.2 revealed minor fixes)**

If any fixes were needed in Steps 5.1–5.3, commit them as `chore: address integration test findings`. Otherwise, skip this step.

---

## Self-Review

**1. Spec coverage:**
- Section 1 (Problem) — addressed in plan overview
- Section 2 (Goals 1–4) — T1 (skills), T3 (guardrail), T2 (subagent), T1+T4 (parallel runtime)
- Section 4 (File Layout) — T1 (skills), T2 (agent), T3 (opencode.json), T4 (AGENTS.md)
- Section 5 (Skill Adaptations) — reflected in T1 skill content
- Section 6 (oc-translator) — T2 verbatim
- Section 7 (opencode.json guardrails) — T3 verbatim
- Section 8 (Sequential loop) — embedded in T1's `oc-translate-book` SKILL.md content
- Section 9 (AGENTS.md cross-reference) — T4 verbatim
- Section 10 (Test Strategy) — T1–T4 each produce one of the 4 test files
- Section 11 (Data Flow) — described in T1's `oc-translate-book` SKILL.md content
- Section 12 (Error Handling) — described in T1's `oc-translate-book` SKILL.md content
- Section 13 (Acceptance Criteria 1–5) — T1–T5 cover all 5
- Section 13 (Acceptance Criteria 6–7) — manual; documented in T5
- Section 14 (Out-of-scope trade-offs) — documented in spec and in `oc-translate-book` body

**2. Placeholder scan:** No "TBD", "TODO", "implement later", "similar to Task N", or vague placeholders. Every step contains the actual content (file content, command, expected output).

**3. Type consistency:** `oc-translator` referenced as `oc-translator` everywhere. The `task({subagent_type: "oc-translator", ...})` signature is consistent across the SKILL.md dispatch template and the subagent frontmatter. Skill names use `oc-` prefix consistently. JSON permission rule keys use the exact patterns from the spec (no typos).

**Found and fixed inline during review:**
- Initial draft of `test_translator_read_write_glob_grep_enabled` had a regex escape bug; fixed in T2 Step 2.1.
- T3 Step 3.3 initially had the `permission` block below `plugin`; reordered to match the spec ordering (`$schema`, `plugin`, `permission`).
- T4 Step 4.3 anchor instruction was vague; clarified to "read last 5 lines of AGENTS.md first, then use that as `oldString`".
