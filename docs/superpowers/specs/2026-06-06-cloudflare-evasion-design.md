# Spec: Cloudflare Bypass & Evasions for crawl-book Skill

* **Date**: 2026-06-06
* **Status**: Approved
* **Author**: Antigravity

## Goal
Improve the `crawl-book` skill instructions (`.agent/skills/crawl-book/SKILL.md`) to dynamically guide agents and users on implementing and troubleshooting Cloudflare bypass mechanisms (Playwright, browser evasions, stateful session cookie pre-fetching, self-healing loops, and character count threshold adjustments).

## Proposed Changes

### 1. Main Skill File: [.agent/skills/crawl-book/SKILL.md](../../../.agent/skills/crawl-book/SKILL.md)
Add a dedicated "Handling Cloudflare, Anti-Bot & Evasions" section explaining the browser setup, evasion rules, cookie pre-fetching, self-healing loop, and character threshold adjustments.

### 2. Claude Code Mirror: [.claude/skills/crawl-book/SKILL.md](../../../.claude/skills/crawl-book/SKILL.md)
Mirror the same additions to keep the Claude Code skill folder synchronized.

### 3. OpenCode Mirror: [.opencode/skill/oc-crawl-book/SKILL.md](../../../.opencode/skill/oc-crawl-book/SKILL.md)
Mirror the same additions to keep the OpenCode-native skill folder synchronized.

## Evasion Mechanics Details
1. **Automation Flag Bypass**: Launch Chromium with `--disable-blink-features=AutomationControlled` to prevent detection.
2. **Object.webdriver Deletion**: Delete `navigator.webdriver` from the navigator prototype contextually prior to page load.
3. **Index Pre-Fetch**: Visit `https://www.69shuba.com/book/<book_id>/` first to acquire session cookies before crawling chapter text URLs.
4. **Self-Healing Loop**: Poll the page title every 1s for up to 10s to dynamically resolve Cloudflare's `Just a moment...` challenge page.
5. **Character Threshold Override**: Lower `min_chapter_characters` locally in `crawl-profile.yaml` to accept short pages (e.g. author notices).

## Verification Plan
1. Ensure the markdown structure and formatting of the updated skill files are clean.
2. Verify all references to codebase files and paths are correct.
