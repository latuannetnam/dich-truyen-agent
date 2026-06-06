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
  prompt: "Execute the translation loop for the next 20 pending chapters sequentially. For each chapter, query progress, prepare context, spawn cc_translator, verify staging, and promote."
})
```
