Use Claude Code native `Agent` dispatch.

Metadata translation uses `cc_metadata_translator`:
```text
Agent({
  subagent_type: "cc_metadata_translator",
  prompt: "Translate the metadata for the book. Title: '<title>', Author: '<author>'"
})
```

Coordinator dispatch uses `cc_coordinator`, and the coordinator dispatches each chapter to `cc_translator`:
```text
Agent({
  subagent_type: "cc_coordinator",
  prompt: "Execute the compact translation loop for the next <batch_size> pending chapters sequentially, where <batch_size> comes from show-translation-settings data.batch_size unless the user supplied an explicit override. For each chapter, fetch next-translation-work-item, spawn cc_translator, verify staging through verify-staged-chapter, and promote. Return only {status, processed_count, chapter_start, chapter_end, next_chapter_id, failure_reason}."
})
```

### Cowork Fallback Dispatch (built-in general agent)

Claude Cowork reads these same `cc-*` adapters, but its `Agent` tool exposes only
built-in agents — `cc_coordinator`, `cc_translator`, and `cc_metadata_translator`
are **not dispatchable** there — and Cowork's Linux sandbox cannot use the
committed Windows `.venv`. When you are running under Cowork:

- Run every CLI command as
  `UV_CACHE_DIR=/tmp/uv-cache uv run --isolated --python 3.13 main.py <command>`
  instead of the `python main.py` form.
- Do **not** spawn a Coordinator Subagent. The **Main Agent itself** runs the
  compact per-chapter loop (fetch `next-translation-work-item` → dispatch one
  translator worker → `verify-staged-chapter` → `promote-chapter`), repeating up
  to the effective `batch_size`. This is the Coordinator's job done inline, with
  **no separate subagent tier**.
- For each chapter, dispatch the built-in general agent as the translator worker:
  ```text
  Agent({
    subagent_type: "general-purpose",
    prompt: "Read and follow .claude/agents/cc_translator.md exactly. Translate the assigned chapter using the absolute paths reported by next-translation-work-item, including glossary_context_path. Return only the translator's compact JSON result."
  })
  ```
- For metadata translation (skill Step 1.5), dispatch the built-in general agent
  instructed to read and follow `.claude/agents/cc_metadata_translator.md`.
- The Main Agent must still never read raw Chinese or completed Vietnamese
  chapters; the dispatched general worker is the only reader of raw chapter files.
  This preserves the token-protection model without the custom coordinator and
  translator agents.
