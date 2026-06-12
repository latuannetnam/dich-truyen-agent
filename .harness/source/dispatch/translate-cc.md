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
