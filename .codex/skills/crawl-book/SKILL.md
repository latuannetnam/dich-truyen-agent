---
name: "crawl-book"
description: "Crawl a novel into a validated local workspace"
metadata:
  short-description: "Crawl a novel into a validated local workspace"
---

# Crawl Book

Crawl a Chinese novel sequentially and resume downloads into a local workspace using robust static parsing and headless browser fallback.

## Workflow

1. **Initialize or Resume Crawl**:
   Execute the deterministic crawl helper:
   ```bash
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
     ```bash
     uv run python main.py validate-crawl-profile --workspace books/<book-slug> --profile books/<book-slug>/crawl-profile.yaml
     ```
   - Promote the local override to shared templates if appropriate:
     ```bash
     uv run python main.py promote-crawl-profile --workspace books/<book-slug>
     ```

3. **Verify and Audit the Report**:
   Inspect the structured crawl report written under `reports/crawl.yaml`.
   - Verify completed, discovered, and failed counts.
   - Review warning residue findings or chapter length anomalies.

4. **Approve Crawl**:
   Create a hash-backed, scope-aware `crawl-approved` checkpoint:
   ```bash
   uv run python main.py approve-crawl --workspace books/<book-slug> [--max-chapters <limit>]
   ```
   - Approval evidence will cover `reports/crawl.yaml` and every raw file in download scope.
   - The checkpoint is saved under `checkpoints/crawl-approved.yaml` and is verified by downstream phases.
