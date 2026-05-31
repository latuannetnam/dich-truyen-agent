---
status: complete
---

# Remove tracked local Claude Code and Codex settings - Summary

- Added exact `.gitignore` rules for `.claude/settings.local.json` and `.codex/config.toml`.
- Removed both settings files from Git tracking with `git rm --cached`.
- Preserved both local files on disk for local Claude Code and Codex use.
- Implementation commits: `7e05f4f`, `745a514`.
