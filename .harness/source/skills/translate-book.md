# {SKILL_TITLE}

Thin compatibility entrypoint for the chapter translation phase of the novel translation pipeline. Maps directly to the shared orchestrator with `--start-at translate --stop-after translate`.

## Workflow

1. **Execute Chapter Translation**:
   Run chapter translation through the orchestrator:
   ```powershell
   $env:PYTHONUTF8=1
   uv run python main.py orchestrate --workspace books/<book-slug> --start-at translate --stop-after translate [--batch-size 5] [--agy-translation-model <model-slug>]
   ```
   - Automatically translates book metadata if not already translated.
   - Dispatches one isolated fresh agent process per chapter.
   - Enforces strict narrative predecessor context and attempt-scoped staging verification.
   - Atomically promotes completed chapters and records progress in checkpoints.

2. **Handle Paused or Blocked Runs**:
   - If blocked on a missing prerequisite (e.g. crawl gate missing or partial), resolve the prerequisite first.
   - Resume an interrupted translation run:
     ```powershell
     $env:PYTHONUTF8=1
     uv run python main.py orchestrate --workspace books/<book-slug> --resume
     ```

## Context Protection & Guardrails

- Do NOT read raw source Chinese files or completed Vietnamese chapters into your Main Agent session.
- Do NOT use external LLM APIs; translation is performed exclusively by isolated native workers dispatched by the orchestrator.

See the orchestrate-book skill for full parameter reference and resume workflows.
