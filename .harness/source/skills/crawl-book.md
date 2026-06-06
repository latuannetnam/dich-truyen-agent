# {SKILL_TITLE}

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

3. **Handling Cloudflare, Anti-Bot & Evasions**:
   If the target site employs Cloudflare or other anti-bot protection (e.g., www.69shuba.com):
   - **Automation Flag Bypass**: Launch Chromium with evasion flags such as `--disable-blink-features=AutomationControlled` to prevent detection.
   - **Remove webdriver Property**: Ensure `navigator.webdriver` is removed or overwritten (`Object.defineProperty(navigator, 'webdriver', {get: () => undefined})`) before navigation starts.
   - **Session Cookie Pre-Fetching**: Prior to extracting chapter contents, visit the book index/catalog page (e.g., `https://www.69shuba.com/book/<book_id>/`) in the browser context. This allows Cloudflare to set necessary security session cookies (like `cf_clearance`).
   - **Self-Healing Loop for Challenge Pages**: Implement a loop that checks the page title for challenge text (e.g., "Just a moment...", "Attention Required!"). If detected, poll every 1 second for up to 10 seconds to allow background verification processes to complete instead of failing immediately.
   - **Validation Overrides**: When short author notice chapters or status updates (e.g., 70-80 characters) trigger chapter length warnings, edit the local `crawl-profile.yaml` inside the workspace to lower `min_chapter_characters` (e.g., set to `20`) to allow these chapters to pass validation.

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
