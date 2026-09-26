---
name: codex-check-translation
description: "Use when running the check-translation phase of the Chinese-to-Vietnamese novel translation pipeline in the codex harness."
---

<!-- GENERATED from .harness/source by tools/sync_harness_adapters.py. Do not edit directly. -->

# Codex-Check Translation

Thin compatibility entrypoint for the quality assurance phase of the novel translation pipeline. Maps directly to the shared orchestrator with `--start-at qa --stop-after qa`.

## Workflow

1. **Execute QA Scan**:
   Run deterministic quality assurance through the orchestrator:
   ```powershell
   $env:PYTHONUTF8=1
   uv run python main.py orchestrate --workspace books/<book-slug> --start-at qa --stop-after qa
   ```
   - Audits all translated chapters for structural consistency, Chinese residue, abnormal length ratios, and glossary conflicts.
   - Non-mutating scan outputs `reports/qa-report.yaml`.
   - If zero errors and zero warnings are found, QA approval is granted automatically and recorded in the `qa-approved` checkpoint.

2. **Handle Findings and Approval**:
   - If warnings are present, the run pauses for manual operator decision (exit code 2). Inspect `reports/qa-report.yaml` and resume:
     ```powershell
     $env:PYTHONUTF8=1
     uv run python main.py orchestrate --workspace books/<book-slug> --resume --decision approve
     ```
   - If critical errors are found, the run blocks (exit code 3). Fix reported issues in translation files, then rerun.

See the orchestrate-book skill for full parameter reference and resume workflows.
