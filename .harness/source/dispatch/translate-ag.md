Use Antigravity native subagent dispatch with `invoke_subagent`.

Metadata translation uses `ag_metadata_translator`:
```json
invoke_subagent({
  "Subagents": [
    {
      "Prompt": "Translate the metadata for the book. Title: '<title>', Author: '<author>'",
      "Role": "Chinese-to-Vietnamese Xianxia/Tu Chan Metadata Translator",
      "TypeName": "ag_metadata_translator"
    }
  ]
})
```

Coordinator dispatch uses `ag_coordinator`, and the coordinator dispatches each chapter to `ag_translator`:
```json
invoke_subagent({
  "Subagents": [
    {
      "Prompt": "Execute the compact translation loop for the next <batch_size> pending chapters sequentially, where <batch_size> comes from show-translation-settings data.batch_size unless the user supplied an explicit override. For each chapter, fetch next-translation-work-item, spawn ag_translator, verify staging through verify-staged-chapter, and promote. Return only {status, processed_count, chapter_start, chapter_end, next_chapter_id, failure_reason}.",
      "Role": "Translation Coordinator",
      "TypeName": "ag_coordinator"
    }
  ]
})
```
