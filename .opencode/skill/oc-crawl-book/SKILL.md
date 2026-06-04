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
