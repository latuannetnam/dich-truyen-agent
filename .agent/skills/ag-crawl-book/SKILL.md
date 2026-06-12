---
name: "ag-crawl-book"
description: "Use when running the crawl-book phase of the Chinese-to-Vietnamese novel translation pipeline in the ag harness."
metadata:
  short-description: "Use when running the crawl-book phase of the Chinese-to-Vietnamese novel translation pipeline in the ag harness."
---

<!-- GENERATED from .harness/source by tools/sync_harness_adapters.py. Do not edit directly. -->

# AG-Crawl Book

Crawl a Chinese novel sequentially and resume downloads into a local workspace using robust static parsing and headless browser fallback. Use the active harness command-execution capability for CLI commands and the active harness file-reading capability for bounded report inspection.

## Workflow

1. **Initialize or Resume Crawl**:
   Execute the deterministic crawl helper:
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

3. **Handling Dynamic Browser And Anti-Bot Cases**:
   If the target site needs JavaScript rendering, session warmups, challenge waits, or browser evasions, prefer a local `crawl-profile.yaml` override:
   ```yaml
   browser:
     enabled: true
     strategy: noop
     launch_args:
       - "--disable-blink-features=AutomationControlled"
     init_scripts:
       - "delete Object.getPrototypeOf(navigator).webdriver;"
     challenge:
       title_markers:
         - "just a moment"
         - "attention required"
       max_wait_seconds: 15
       poll_seconds: 1.0
     session:
       warmups:
         - url_pattern: "https?://example\\.com/txt/(?P<book_id>\\d+)/\\d+"
           warmup_url: "https://example.com/book/{book_id}/"
     actions:
       - purpose: index
         action: click
         selector: ".catalog-all"
         wait_for_selector: ".clist .u-chapter li a"
   ```
   - Use declarative profile settings for common browser behavior: launch arguments, user agent, viewport, init scripts, challenge title polling, warmup URLs, response waits, selector waits, and simple clicks.
   - Use `browser.strategy: <name>` only when the behavior is too procedural for YAML and the named browser strategy exists in the Python strategy registry.
   - Do not hardcode site-specific browser behavior in `browser.py`; keep new site behavior in the active crawl profile or a small named browser strategy.
   - Promote the local override to shared templates only after validating it against the source domain.

4. **Verify and Audit the Report**:
   Inspect the structured crawl report written under `reports/crawl.yaml` using bounded file-reading.
   - Verify completed, discovered, and failed counts.
   - Review warning residue findings or chapter length anomalies.

5. **Approve Crawl**:
   Create a hash-backed, scope-aware `crawl-approved` checkpoint:
   ```powershell
   $env:PYTHONUTF8=1
   uv run python main.py approve-crawl --workspace books/<book-slug> [--max-chapters <limit>]
   ```
   - Approval evidence will cover `reports/crawl.yaml` and every raw file in download scope.
   - The checkpoint is saved under `checkpoints/crawl-approved.yaml` and is verified by downstream phases.

## Runtime Notes

- Use the active harness command tool to execute CLI commands.
- Use the active harness file reader to inspect `reports/crawl.yaml`, `chapters.yaml`, and `state.yaml`.
- Do NOT read raw Chinese chapter files (`books/<book-slug>/raw/*.txt`) into your main context - they overflow the window. Trust the CLI report summaries.
- Do not run commands that reference banned external LLM endpoints, env vars, or import patterns. Use the native harness translator subagent for translation work.
