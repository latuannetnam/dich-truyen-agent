Use `spawn_agent` for native Codex subagent delegation.

Metadata translation uses `codex_metadata_translator`, and chapter translation uses `codex_translator`:
```text
spawn_agent(
  type="codex_coordinator",
  prompt="Execute the compact translation loop for the next <batch_size> pending chapters sequentially, where <batch_size> comes from show-translation-settings data.batch_size unless the user supplied an explicit override. For each chapter, fetch next-translation-work-item, spawn codex_translator, verify staging through verify-staged-chapter, and promote. Return only {status, processed_count, chapter_start, chapter_end, next_chapter_id, failure_reason}."
)
```

This path must use native Codex subagent delegation only, never external LLM APIs.
