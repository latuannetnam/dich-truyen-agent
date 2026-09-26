### Claude Cowork Panel

- Claude Cowork is **built on Claude Code** and reads the same `.claude/` plugin adapters. Run the Claude Code pipeline skills directly: `cc-orchestrate-book`, `cc-crawl-book`, `cc-translate-book`, `cc-check-translation`, and `cc-export-book`. There is no separate `cw-*` adapter set.
- **CLI form under Cowork's Linux sandbox:** The committed `.venv` is a Windows virtualenv and is unusable in Cowork's Linux sandbox. Run every CLI command in an isolated, ephemeral environment:
  ```bash
  UV_CACHE_DIR=/tmp/uv-cache uv run --isolated --python 3.13 main.py <command>
  ```
- **Token protection still holds:** The Main Agent handles only CLI JSON and dispatch. Never read raw Chinese or completed Vietnamese chapters into the Main Agent session.
- **Cowork hooks do not fire:** The `check_external_llm.py` guardrail hook is inert under Cowork, so the external-LLM prohibition is enforced at **instruction level** inside the skills. Never use an external LLM API to translate.
