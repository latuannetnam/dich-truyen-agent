---
name: cc-crawl-book
description: "Use when running the crawl-book phase of the Chinese-to-Vietnamese novel translation pipeline in the cc harness."
---

<!-- GENERATED from .harness/source by tools/sync_harness_adapters.py. Do not edit directly. -->

# CC-Crawl Book

Thin compatibility entrypoint for the crawl phase of the novel translation pipeline. Maps directly to the shared orchestrator with `--start-at crawl --stop-after crawl`.

## Workflow

1. **Execute Crawl**:
   Run crawl through the orchestrator:
   ```powershell
   $env:PYTHONUTF8=1
   uv run python main.py orchestrate --workspace books/<book-slug> --start-at crawl --stop-after crawl
   ```
   - Discovers catalog in `chapters.yaml` and downloads raw text chapters to `raw/`.
   - Automatic local profile repair is invoked if catalog discovery or extraction encounters issues.
   - If zero warnings/blockers are present and `--auto-approve` is set, crawl approval is granted automatically.

2. **Handling Dynamic Browser And Anti-Bot Cases**:
   If the target site needs JavaScript rendering, session warmups, challenge waits, or browser evasions, configure declarative `browser:` settings in `crawl-profile.yaml`:
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

3. **Handle Paused or Blocked Runs**:
   - If the run returns status `paused` (exit code 2), inspect `reports/crawl.yaml` using bounded file-reading and resume:
     ```powershell
     $env:PYTHONUTF8=1
     uv run python main.py orchestrate --workspace books/<book-slug> --resume --decision approve
     ```
   - If status is `blocked` (exit code 3), inspect the error reason in terminal output and address blockers before retrying.

See the orchestrate-book skill for full parameter reference and resume workflows.
