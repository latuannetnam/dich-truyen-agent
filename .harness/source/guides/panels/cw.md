### Claude Cowork Panel

- Claude Cowork is **built on Claude Code** and reads the same `.claude/` plugin adapters. Run the Claude Code pipeline skills directly: `cc-crawl-book`, `cc-translate-book`, `cc-check-translation`, and `cc-export-book`. There is no separate `cw-*` adapter set.
- Use `Bash` for CLI commands (`uv run python main.py ...`) and `Read` for bounded file inspection.
- Coordinator and translator delegation uses the same `cc_coordinator` and `cc_translator` `Agent` dispatch as Claude Code.
- **Cowork hooks do not fire.** The `check_external_llm.py` guardrail hook is inert under Cowork, so the external-LLM prohibition is enforced at **instruction level** inside the skills and agents instead. Do not rely on hook blocking in Cowork.
- **Always verify subagent dispatch in Cowork before running large books.** Skill-body subagent dispatch is undocumented in Cowork; the token-protection model requires the translator subagent to be the only worker that reads raw chapter files. Confirm dispatch works on a small book first.
