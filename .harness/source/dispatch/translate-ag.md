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
      "Prompt": "Execute the translation loop for the next 20 pending chapters sequentially. For each chapter, query progress, prepare context, spawn ag_translator, verify staging, and promote.",
      "Role": "Translation Coordinator",
      "TypeName": "ag_coordinator"
    }
  ]
})
```
