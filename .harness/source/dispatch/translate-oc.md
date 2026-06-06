Use OpenCode native `task(` dispatch with `subagent_type="general"`.

Metadata translation runs through the general task path with metadata-specific instructions. Chapter translation delegates to `oc-translator`:
```text
task(
  subagent_type="general",
  description="Translate the next chapter with oc-translator",
  prompt="Use oc-translator instructions to translate the assigned chapter from the prepared context paths."
)
```

OpenCode embeds the sequential loop in the `oc-translate-book` skill body and uses `task(` for each isolated chapter worker.
