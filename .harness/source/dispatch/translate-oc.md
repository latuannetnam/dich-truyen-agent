Use OpenCode native `task(` dispatch with `subagent_type="general"`.

Metadata translation runs through the general task path with metadata-specific instructions. Chapter translation delegates to `oc-translator`:
```text
task(
  subagent_type="general",
  description="Translate the next chapter with oc-translator",
  prompt="Use oc-translator instructions to translate the assigned chapter from the next-translation-work-item paths."
)
```

OpenCode embeds the compact sequential loop in the `oc-translate-book` skill body, uses `show-translation-settings` for the effective `batch_size`, and uses `task(` for each isolated chapter worker.
