Use `spawn_agent` for native Codex subagent delegation.

Metadata translation uses `codex_metadata_translator`, and chapter translation uses `codex_translator`:
```text
spawn_agent(
  type="codex_coordinator",
  prompt="Execute the translation loop for the next 20 pending chapters sequentially. For each chapter, query progress, prepare context, spawn codex_translator, verify staging, and promote."
)
```

This path must use native Codex subagent delegation only, never external LLM APIs.
